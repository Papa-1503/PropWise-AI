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
    see _match_caller_to_resident below.
  - Start a real AI triage conversation (see voice_triage_service.py)
    to find out what's wrong and which unit, create a real maintenance
    ticket from it, then route the call based on the ticket's real
    computed severity: emergency/urgent with a tech on file connects
    the call now; otherwise the caller is told it's logged and the
    call ends. Every call is also logged to the audit trail
    (routers/audit.py) with the match result, whether or not one was
    found.
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

from db import properties_col, on_call_shifts_col, users_col, leases_col, on_call_log_col, voice_triage_col
from phone_utils import normalize_phone
from audit_service import log_action
from auth import require_staff
import voice_triage_service
from services.ticket_severity import compute_severity
from routers.maintenance import create_ticket_document
from routers.photo_upload import create_upload_token
import sms_service

router = APIRouter(prefix="/api/telephony", tags=["telephony"])


def _validate_twilio_signature(request: Request, form_dict: dict, signature: str) -> None:
    token = os.getenv("TWILIO_AUTH_TOKEN")
    if not token:
        # Fail closed, not open - an unconfigured server should reject
        # every call, not silently accept unsigned ones.
        raise HTTPException(status_code=503, detail="Telephony not configured on this server.")
    validator = RequestValidator(token)
    # BUG FIX (found by checking the real audit log after two live test
    # calls showed ZERO after_hours_call_routed entries - proof the
    # webhook logic never got past this line): str(request.url) reflects
    # the scheme our server actually SEES the request arrive on, not the
    # scheme Twilio actually signed. Render terminates HTTPS and forwards
    # internally over plain HTTP, and no proxy-header trust is configured
    # (no --proxy-headers on the uvicorn start command, no
    # ProxyHeadersMiddleware) - so request.url reports "http://...", while
    # Twilio always signs the real public "https://..." URL it called.
    # Validating against the wrong scheme fails EVERY signature check,
    # rejecting every real call with a 403 before any routing logic runs.
    # Rebuilding the URL from the known public domain (same approach
    # already used for the recording/transcription callback URLs) sidesteps
    # the scheme-detection problem entirely rather than depending on
    # infrastructure-level proxy header configuration.
    public_url = f"https://rentflow-ai.onrender.com{request.url.path}"
    if request.url.query:
        public_url += f"?{request.url.query}"
    if not validator.validate(public_url, form_dict, signature):
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

    # AI phone triage starts here instead of dialing/voicemail
    # immediately - see voice_triage_service.py's module docstring for
    # the full reasoning (Gather-based turn exchange, not real-time
    # Media Streams). State is kept in voice_triage_col, keyed by
    # Twilio's own CallSid, since Twilio itself carries no state
    # between this request and the /voice-ai-turn callback below.
    call_sid = form_dict.get("CallSid")
    known_unit = matched_lease.get("unitId") if matched_lease else None
    await voice_triage_col.insert_one({
        "callSid": call_sid,
        "propertyId": property_id,
        "callerNumber": caller_number,
        "knownUnit": known_unit,
        "matchedResidentName": matched_lease.get("residentName") if matched_lease else None,
        "techPhone": tech_phone,
        "turns": [],
        "pendingQuestion": voice_triage_service.FIRST_QUESTION,
        "ticketId": None,
        "createdAt": now,
    })

    gather = response.gather(
        input="speech", action="/api/telephony/voice-ai-turn", method="POST",
        speech_timeout="auto", timeout=8,
    )
    gather.say(voice_triage_service.FIRST_QUESTION)
    # Falls through here only if Gather's own timeout expires with no
    # speech captured at all - never leaves a silent caller with dead
    # air, falls back to the same real voicemail recording this line
    # always had.
    response.say("Sorry, I didn't catch that. Please leave a message after the tone and our team will call you back.")
    response.record(max_length=120, play_beep=True)

    return Response(content=str(response), media_type="application/xml")


@router.post("/voice-ai-turn")
async def voice_ai_turn(request: Request):
    """Handles each real <Gather> callback during an after-hours AI
    triage call - one caller answer in, one AI decision out. See
    voice_triage_service.py for the actual conversation logic; this
    endpoint's job is just real state management (persisting each
    turn) and turning the AI's decision into real TwiML, a real
    ticket, and real call routing."""
    form = await request.form()
    form_dict = dict(form)
    signature = request.headers.get("X-Twilio-Signature", "")
    _validate_twilio_signature(request, form_dict, signature)

    call_sid = form_dict.get("CallSid")
    speech_result = form_dict.get("SpeechResult", "")
    response = VoiceResponse()

    triage_doc = await voice_triage_col.find_one({"callSid": call_sid})
    if not triage_doc:
        # Real, if rare, edge case - triage state genuinely missing
        # (e.g. a server restart mid-call). Never leave the caller
        # stuck - fall back to the same voicemail path every other
        # unhandled case in this file uses.
        response.say("Sorry, something went wrong on our end. Please leave a message after the tone.")
        response.record(max_length=120, play_beep=True)
        return Response(content=str(response), media_type="application/xml")

    turns = triage_doc.get("turns", [])
    turns.append({"question": triage_doc.get("pendingQuestion"), "answer": speech_result})

    decision = await voice_triage_service.next_step(turns, triage_doc.get("knownUnit"))

    if decision["action"] == "ask":
        await voice_triage_col.update_one(
            {"callSid": call_sid},
            {"$set": {"turns": turns, "pendingQuestion": decision["question"]}},
        )
        gather = response.gather(
            input="speech", action="/api/telephony/voice-ai-turn", method="POST",
            speech_timeout="auto", timeout=8,
        )
        gather.say(decision["question"])
        response.say("Sorry, I didn't catch that. Please leave a message after the tone and our team will call you back.")
        response.record(max_length=120, play_beep=True)
        return Response(content=str(response), media_type="application/xml")

    # action == "conclude": create a real ticket through the exact same
    # pipeline every other ticket in this app goes through (dedup,
    # real severity scoring, auto-assignment, notifications) - see
    # routers/maintenance.py's create_ticket_document.
    unit_id = triage_doc.get("knownUnit") or decision.get("unitId") or "unknown-caller-unmatched"
    title = decision.get("title") or "After-hours call - details unclear"
    category = decision.get("category") or "general"

    # Precomputed here (in addition to the real, authoritative
    # recompute inside create_ticket_document) only to decide the
    # self-reported `priority` field passed in, which drives whether
    # create_ticket_document's own notification fires as urgent - both
    # calls are the same deterministic function on the same title/
    # category, so they can never actually disagree.
    pre_severity = compute_severity(title, category)
    ticket_doc = {
        "propertyId": triage_doc["propertyId"],
        "unitId": unit_id,
        "title": title,
        "description": decision.get("description") or "",
        "category": category,
        "priority": "urgent" if pre_severity["tier"] in ("emergency", "urgent") else "normal",
        "source": "resident",
    }
    ticket_result = await create_ticket_document(ticket_doc)
    severity_tier = ticket_result.get("severityTier", "routine")

    await voice_triage_col.update_one(
        {"callSid": call_sid},
        {"$set": {"turns": turns, "pendingQuestion": None, "ticketId": ticket_result.get("id"), "severityTier": severity_tier}},
    )
    # A spoken URL isn't usable, so the photo-upload link goes out as a
    # real, separate SMS to the caller's own number instead - same
    # token-issuing logic routers/sms_inbound.py uses for its text-in
    # flow. Never blocks call routing if the SMS send itself fails
    # (e.g. a landline that can't receive texts) - the ticket is
    # already real either way, a photo is a bonus, not a requirement.
    try:
        upload_token = await create_upload_token(ticket_result.get("id"), triage_doc["propertyId"], unit_id)
        upload_link = f"https://rentflow-ai-1.onrender.com/upload-photos/{upload_token}"
        await sms_service.send_sms_async(
            triage_doc.get("callerNumber"),
            f"PropWise AI: we logged your maintenance request ({title}). "
            f"If you have a photo, send it here (link expires in 48h): {upload_link}",
        )
    except Exception:
        pass
    tech_phone = triage_doc.get("techPhone")
    if severity_tier in ("emergency", "urgent") and tech_phone:
        response.say(f"Thanks - I've logged this as {title}. Connecting you to our on-call technician now.")
        response.dial(tech_phone, record="record-from-answer-dual", recording_status_callback="https://rentflow-ai.onrender.com/api/telephony/recording-status")
    else:
        response.say(
            f"Thanks - I've logged a maintenance ticket for {title}. "
            f"Our team will follow up during regular business hours. Have a good night."
        )

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
                    transcribe_callback="https://rentflow-ai.onrender.com/api/telephony/transcription-status"
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


@router.get("/triage-log")
async def list_triage_log(user: dict = Depends(require_staff)):
    """The real AI conversation itself (each question asked, each real
    answer given) for every after-hours AI-triaged call - distinct
    from /call-log above, which is the raw recording/transcription of
    the human portion of the call (after a tech picks up), not the
    structured Q&A the AI ran beforehand. This was real, stored data
    (voice_triage_col) with no staff-facing view before this - the
    only way to see it was a direct database query."""
    docs = await voice_triage_col.find({}).sort("createdAt", -1).to_list(length=200)
    property_ids = {d.get("propertyId") for d in docs if d.get("propertyId")}
    properties = {}
    for pid in property_ids:
        query_id = ObjectId(pid) if ObjectId.is_valid(pid) else pid
        prop = await properties_col.find_one({"_id": query_id})
        if prop:
            properties[pid] = prop.get("name")

    for d in docs:
        d["id"] = str(d.pop("_id"))
        d["propertyName"] = properties.get(d.get("propertyId"))
        if isinstance(d.get("createdAt"), datetime):
            d["createdAt"] = d["createdAt"].isoformat()

    return {"triageLog": docs}
