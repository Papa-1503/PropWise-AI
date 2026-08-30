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
  - Look up that person's phone (users_col.phone, set via
    PATCH /api/staff/{id}/phone) and dial it
  - Otherwise (no on-call shift, no phone on file, or outside the
    after-hours window) fall back to an honest spoken message rather
    than silently dropping the call or dialing nothing

Security: every request is verified against Twilio's request signature
(X-Twilio-Signature header) using TWILIO_AUTH_TOKEN, the same token
already used for outbound SMS in sms_service.py. An unsigned or
incorrectly-signed request is rejected with 403 before any TwiML is
generated - this endpoint is public (Twilio can't authenticate as a
RentFlow user), so signature validation is the only thing standing
between it and anyone who finds the URL and POSTs fake call data to it.
"""
import os
from datetime import datetime, time, timezone

from bson import ObjectId
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import Response
from twilio.request_validator import RequestValidator
from twilio.twiml.voice_response import VoiceResponse

from db import properties_col, on_call_shifts_col, users_col

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
    on_call_shift = await on_call_shifts_col.find_one({
        "propertyIds": property_id,
        "startTime": {"$lte": now},
        "endTime": {"$gte": now},
    })

    tech_phone = None
    if on_call_shift and ObjectId.is_valid(on_call_shift.get("userId", "")):
        tech = await users_col.find_one({"_id": ObjectId(on_call_shift["userId"])})
        tech_phone = tech.get("phone") if tech else None

    if tech_phone:
        response.dial(tech_phone)
    else:
        response.say(
            "Thanks for calling. Nobody is currently available to take "
            "your call. Please leave a message after the tone and our "
            "on-call team will call you back."
        )
        response.record(max_length=120, play_beep=True)

    return Response(content=str(response), media_type="application/xml")
