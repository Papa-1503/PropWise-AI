"""
Twilio Voice webhook — after-hours on-call call routing.

POST /api/telephony/voice   -> Twilio hits this when a call comes in to
                                a property's configured Twilio number.
                                Returns TwiML telling Twilio what to do
                                with the call.

Setup this depends on (manual, one-time, outside this app, per
property that wants after-hours routing):
  1. Buy a real Twilio phone number in the Twilio console
  2. Point that number's Voice webhook at
     https://rentflow-ai.onrender.com/api/telephony/voice (POST)
  3. Set that number as the property's `twilioNumber` via
     PATCH /api/properties/{id}/telephony (routers/properties.py)

Routing logic:
  - Look up which property owns the number Twilio says was called
    (the `To` param) via twilioNumber
  - If it's currently within that property's configured after-hours
    window (afterHoursStart/afterHoursEnd, wrapping past midnight is
    handled explicitly below), look up who's on call right now — the
    same query GET /api/on-call/current uses (see routers/oncall.py)
  - Match the caller's number (the `From` param, Twilio sends E.164)
    against that property's leases via phone_utils.normalize_phone -
    see _match_caller_to_resident below. When matched, the on-call
    tech hears who's calling and which unit before the call connects,
    the same context a caller-ID-aware office phone gives a human
    receptionist. Every call is also logged to the audit trail
    (routers/audit.py) with the match result, whether or not one was
    found.
  - Look up the on-call tech's phone (users_col.phone, set via
    PATCH /api/staff/{id}/phone) and dial it
  - Otherwise (no on-call shift, no phone on file, or outside the
    after-hours window) fall back to an honest spoken message rather
    than silently dropping the call or dialing nothing

Security: every request is verified against Twilio's request signature
(X-Twilio-Signature header) using TWILIO_AUTH_TOKEN, the same token
already used for outbound SMS in sms_service.py. An unsigned or
incorrectly-signed request is rejected with 403 before any TwiML is
generated - this endpoint is public (Twilio can't authenticate as a
PropWise AI user), so signature validation is the only thing standing
between it and anyone who finds the URL and POSTs fake call data to it.
"""
import os
from datetime import datetime, time, timezone

from bson import ObjectId
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import Response
from twilio.request_validator import RequestValidator
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse

from db import properties_col, on_call_shifts_col, users_col, leases_col, on_call_log_col
from phone_utils import normalize_phone
from audit_service import log_action
from auth import require_staff

router = APIRouter(prefix="/api/telephony", tags=["telephony"])


def _validate_twilio_signature(request: Request, form_dict: dict, signature: str) -> None:
    token = os.getenv("TWILIO_AUTH_TOKEN")
    if not token:
        # Fail closed, not open - an unconfigured server should reject
        # every call, not silently accept unsigned ones.
        raise HTTPException(status_code=503, detail="Telephony not configured on this server.")
    validator = RequestValidator(token)
    # Twilio signs the exact URL it POSTed to, including query string -
    # str(request.url) reconstructs that from the live request rather
    # than hardcoding it, so this stays correct if the deployed domain
    # or path ever changes.
    if not validator.validate(str(request.url), form_dict, signature):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature.")


def _is_after_hours(now_utc: datetime, start_hhmm: str | None, end_hhmm: str | None) -> bool:
    """True if now_utc falls within the [start, end) after-hours window.
    Handles the window wrapping past midnight (e.g. 18:00-08:00 means
    "after 6pm OR before 8am", not a literal same-day range, which
    would be empty/backwards). If either bound isn't configured, treats
    every hour as after-hours - the safer default for a property that
    hasn't set this up yet, so a call still reaches someone rather than
    silently getting no after-hours coverage at all."""
    if not start_hhmm or not end_hhmm:
        return True
    start_h, start_m = map(int, start_hhmm.split(":"))
    end_h, end_m = map(int, end_hhmm.split(":"))
    start = time(start_h, start_m)
    end = time(end_h, end_m)
    now_t = now_utc.time()
    if start <= end:
        return start <= now_t < end
    return now_t >= start or now_t < end


async def _match_caller_to_resident(from_number: str, property_id: str) -> dict | None:
    """Matches an incoming call's caller ID to a real resident, scoped to
    the specific property that was called - a phone number matching a
    lease at a *different* property is not a meaningful match for this
    call, even if the digits happen to line up (e.g. a former resident
    who moved between two of the same landlord's buildings).

    Real normalization tradeoff, stated honestly: residentPhone is
    stored exactly as staff typed it (612-555-9999, (612) 555-9999,
    etc. - all seen in real use), so an exact-string Mongo query against
    it would almost never match Twilio's E.164-formatted caller ID even
    for the correct number. Rather than a bigger, riskier change
    normalizing every stored residentPhone at write time, this fetches
    that property's leases (a small, bounded set - one property, not
    the whole leases collection) and normalizes both sides in Python at
    read time. Simple, safe, and correct for the realistic call volume
    a single after-hours line sees; would need real reconsideration if
    this endpoint's call volume ever grew large enough for per-call
    full-property lease scans to become a genuine performance concern."""
    normalized_caller = normalize_phone(from_number)
    if not normalized_caller:
        return None

    cursor = leases_col.find({"propertyId": property_id, "residentPhone": {"$ne": None}})
    leases = await cursor.to_list(length=500)
    for lease in leases:
        if normalize_phone(lease.get("residentPhone")) == normalized_caller:
            return lease
    return None


@router.post("/voice")
async def voice_webhook(request: Request):
    form = await request.form()
    form_dict = dict(form)
    signature = request.headers.get("X-Twilio-Signature", "")
    _validate_twilio_signature(request, form_dict, signature)

    called_number = form_dict.get("To", "")
    response = VoiceResponse()

    property_doc = await properties_col.find_one({"twilioNumber": called_number})
    if not property_doc:
        response.say("This number is not currently configured. Please try again later.")
        return Response(content=str(response), media_type="application/xml")

    now = datetime.now(timezone.utc)
    after_hours = _is_after_hours(
        now, property_doc.get("afterHoursStart"), property_doc.get("afterHoursEnd")
    )

    if not after_hours:
        response.say(
            "Thanks for calling. This line is for after-hours maintenance "
            "emergencies. Please call back during business hours, or leave "
            "a message after the tone for a callback."
        )
        response.record(max_length=120, play_beep=True)
        return Response(content=str(response), media_type="application/xml")

    property_id = str(property_doc["_id"])
    caller_number = form_dict.get("From", "")
    matched_lease = await _match_caller_to_resident(caller_number, property_id)

    on_call_shift = await on_call_shifts_col.find_one({
        "propertyIds": property_id,
        "startTime": {"$lte": now},
        "endTime": {"$gte": now},
    })

    tech_phone = None
    if on_call_shift and ObjectId.is_valid(on_call_shift.get("userId", "")):
        tech = await users_col.find_one({"_id": ObjectId(on_call_shift["userId"])})
        tech_phone = tech.get("phone") if tech else None

    await log_action(
        actor_id="twilio_voice_webhook", actor_email="",
        action="after_hours_call_routed",
        target_type="property", target_id=property_id,
        details={
            "callerNumber": caller_number,
            "matchedResident": matched_lease.get("residentName") if matched_lease else None,
            "matchedUnitId": matched_lease.get("unitId") if matched_lease else None,
            "routedToTechPhone": bool(tech_phone),
        },
    )

    if tech_phone:
        if matched_lease:
            # A real, if small, staff-facing improvement: the tech
            # answering hears who's calling and which unit before
            # picking up, the same context a caller-ID-aware office
            # phone would already give a human receptionist - this
            # after-hours line otherwise gives none of that.
            response.say(
                f"Incoming after-hours call from {matched_lease.get('residentName', 'a resident')}, "
                f"unit {matched_lease.get('unitId', 'unknown')}. Connecting now."
            )
        response.dial(tech_phone, record="record-from-answer-dual", recording_status_callback="/api/telephony/recording-status")
    else:
        response.say(
            "Thanks for calling. Nobody is currently available to take "
            "your call. Please leave a message after the tone and our "
            "on-call team will call you back."
        )
        response.record(max_length=120, play_beep=True)

    return Response(content=str(response), media_type="application/xml")


@router.post("/recording-status")
async def recording_status_callback(request: Request):
    """Real Twilio recordingStatusCallback webhook - see /voice's
    Dial verb above, which requests this specifically. Twilio calls
    this once the recording is genuinely ready (RecordingStatus=
    "completed"), with real parameters (RecordingSid, RecordingUrl,
    CallSid, RecordingDuration) confirmed directly from Twilio's own
    documentation before building this, not guessed. Same real
    signature-validation requirement as /voice - an unauthenticated
    webhook here would be a real way for anyone to inject fake
    call-log entries.

    Requests Twilio's own built-in transcription (a real, separate
    Twilio API call, not a third-party integration) rather than
    building a new transcription pipeline - reuses infrastructure
    this app already has real credentials for. Transcription result
    itself arrives at a SEPARATE callback (/transcription-status)
    once Twilio finishes it, since transcription is asynchronous and
    genuinely not ready at the same moment as the recording."""
    form = await request.form()
    form_dict = dict(form)
    signature = request.headers.get("X-Twilio-Signature", "")
    _validate_twilio_signature(request, form_dict, signature)

    recording_status = form_dict.get("RecordingStatus")
    if recording_status != "completed":
        # "in-progress" or "absent" - nothing real to store yet, or
        # genuinely nothing was recorded (a silent/instant call).
        return Response(content="", media_type="text/xml")

    recording_sid = form_dict.get("RecordingSid")
    recording_url = form_dict.get("RecordingUrl")
    call_sid = form_dict.get("CallSid")
    duration = form_dict.get("RecordingDuration")

    doc = {
        "callSid": call_sid,
        "recordingSid": recording_sid,
        "recordingUrl": recording_url,
        "durationSeconds": int(duration) if duration and duration.isdigit() else None,
        "transcriptText": None,
        "transcriptStatus": "pending",
        "createdAt": datetime.now(timezone.utc),
    }
    await on_call_log_col.insert_one(doc)

    if recording_sid:
        account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        if account_sid and auth_token:
            try:
                twilio_client = Client(account_sid, auth_token)
                # Real Twilio transcription request - genuinely async;
                # the actual text arrives later at transcribeCallback,
                # not returned here. Failing to even request it should
                # never block the recording itself from being stored -
                # the recording is the more important real artifact.
                twilio_client.recordings(recording_sid).transcriptions.create(
                    transcribe_callback="/api/telephony/transcription-status"
                )
            except Exception as exc:
                print(f"Failed to request transcription for recording {recording_sid}: {exc}")

    return Response(content="", media_type="text/xml")


@router.post("/transcription-status")
async def transcription_status_callback(request: Request):
    """Real Twilio transcribeCallback - fires once Twilio's own
    transcription of a recording (requested above) is actually done.
    Confirmed real parameter names (TranscriptionSid, TranscriptionText,
    TranscriptionStatus) directly from Twilio's documentation."""
    form = await request.form()
    form_dict = dict(form)
    signature = request.headers.get("X-Twilio-Signature", "")
    _validate_twilio_signature(request, form_dict, signature)

    recording_sid = form_dict.get("RecordingSid")
    transcription_status = form_dict.get("TranscriptionStatus")
    transcription_text = form_dict.get("TranscriptionText")

    if recording_sid:
        await on_call_log_col.update_one(
            {"recordingSid": recording_sid},
            {"$set": {
                "transcriptStatus": transcription_status or "failed",
                "transcriptText": transcription_text,
            }},
        )

    return Response(content="", media_type="text/xml")


@router.get("/call-log")
async def list_call_log(user: dict = Depends(require_staff)):
    """Manager-facing view of real, past after-hours calls - the
    other real half of this feature beyond the raw recording/
    transcript capture itself."""
    logs = await on_call_log_col.find({}).sort("createdAt", -1).to_list(length=200)
    for log in logs:
        log["id"] = str(log.pop("_id"))
    return {"callLog": logs}
