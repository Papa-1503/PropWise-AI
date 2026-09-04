"""
Two-way SMS — a resident can text the app's Twilio number to report an
issue, not just receive outbound reminders. Real conversational triage
via voice_triage_service.py (its Q&A logic is medium-agnostic - it
just decides what to ask and when it has enough, regardless of
whether the answer arrives by voice or text), same real ticket
creation pipeline as everything else (create_ticket_document).

POST /api/sms/inbound  -> Twilio hits this on every inbound text to
                           the app's TWILIO_FROM_NUMBER (see
                           sms_service.py). Configure this as that
                           number's Messaging webhook in the Twilio
                           console (one-time manual setup, same
                           pattern as the Voice webhook in
                           routers/telephony.py).

Real difference from the after-hours Voice line: there's exactly ONE
shared Twilio number for all outbound/inbound SMS (TWILIO_FROM_NUMBER),
not one per property the way Voice has (properties_col.twilioNumber).
So a texting resident can't be matched to a property by which number
they texted - only by their own phone number, searched across every
lease's residentPhone (a genuinely larger scan than Voice's
single-property version; same honest performance caveat as
telephony.py's _match_caller_to_resident, worth revisiting if real
inbound SMS volume ever makes a full-collection scan a genuine
concern).

Conversation state: Twilio's inbound SMS webhook carries no session -
each text is a separate, stateless POST. sms_triage_col tracks an
open conversation per phone number, with a real recency cutoff
(CONVERSATION_TIMEOUT_MINUTES) so a resident texting again days later
starts fresh rather than having their new, unrelated text silently
appended as an "answer" to a stale question.

STOP/START/HELP opt-out keywords are handled by Twilio's own Advanced
Opt-Out feature at the carrier/Twilio level before they ever reach
this webhook (default-on for the number types this app uses) - not
reimplemented here, since Twilio's own compliance handling is more
reliable than a bespoke keyword check would be.
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Request
from fastapi.responses import Response
from twilio.twiml.messaging_response import MessagingResponse

from db import leases_col, sms_triage_col
from phone_utils import normalize_phone
from routers.telephony import _validate_twilio_signature
import voice_triage_service
from services.ticket_severity import compute_severity
from routers.maintenance import create_ticket_document

router = APIRouter(prefix="/api/sms", tags=["sms"])

CONVERSATION_TIMEOUT_MINUTES = 30


async def _match_phone_to_resident(phone: str) -> dict | None:
    """Global match across every lease with a residentPhone on file -
    unlike telephony.py's per-property version, there's no property to
    scope this to up front (see module docstring). If more than one
    lease matches the same normalized number (e.g. a reused number
    across two tenancies over time), the most recently started lease
    wins - the real, current resident at that number."""
    normalized_target = normalize_phone(phone)
    if not normalized_target:
        return None

    candidates = await leases_col.find({"residentPhone": {"$ne": None}}).to_list(length=5000)
    matches = [l for l in candidates if normalize_phone(l.get("residentPhone")) == normalized_target]
    if not matches:
        return None
    matches.sort(key=lambda l: l.get("startDate") or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return matches[0]


@router.post("/inbound")
async def sms_inbound(request: Request):
    form = await request.form()
    form_dict = dict(form)
    signature = request.headers.get("X-Twilio-Signature", "")
    _validate_twilio_signature(request, form_dict, signature)

    from_number = form_dict.get("From", "")
    body = (form_dict.get("Body") or "").strip()
    now = datetime.now(timezone.utc)
    response = MessagingResponse()

    # Resume an existing, still-fresh, not-yet-concluded conversation
    # from this number if one exists; otherwise this text starts a new one.
    cutoff = now - timedelta(minutes=CONVERSATION_TIMEOUT_MINUTES)
    triage_doc = await sms_triage_col.find_one({
        "phone": from_number, "concluded": False, "createdAt": {"$gte": cutoff},
    })

    if not triage_doc:
        lease = await _match_phone_to_resident(from_number)
        if not lease:
            response.message(
                "We couldn't match this number to a resident account. "
                "Please call the property office, or report the issue through the app."
            )
            return Response(content=str(response), media_type="application/xml")

        triage_doc = {
            "phone": from_number,
            "propertyId": lease.get("propertyId"),
            "unitId": lease.get("unitId"),
            "residentName": lease.get("residentName"),
            "turns": [],
            "concluded": False,
            "ticketId": None,
            "createdAt": now,
        }
        result = await sms_triage_col.insert_one(triage_doc)
        triage_doc["_id"] = result.inserted_id
        # This first inbound text IS the resident's answer to the
        # implicit "what's going on" opener - no separate canned
        # question needed the way the Voice line's fixed
        # FIRST_QUESTION is, since the resident already texted in
        # with real content rather than being prompted first.
        turns = [{"question": "(resident texted in)", "answer": body}]
    else:
        turns = triage_doc.get("turns", [])
        turns.append({"question": triage_doc.get("pendingQuestion"), "answer": body})

    known_unit = triage_doc.get("unitId")
    decision = await voice_triage_service.next_step(turns, known_unit)

    if decision["action"] == "ask":
        await sms_triage_col.update_one(
            {"_id": triage_doc["_id"]},
            {"$set": {"turns": turns, "pendingQuestion": decision["question"]}},
        )
        response.message(decision["question"])
        return Response(content=str(response), media_type="application/xml")

    # action == "conclude" - same real ticket-creation pipeline every
    # other ticket in this app goes through.
    title = decision.get("title") or "Issue reported via text - details unclear"
    category = decision.get("category") or "general"
    unit_id = known_unit or decision.get("unitId") or "unknown-texted-in"

    severity = compute_severity(title, category)
    ticket_doc = {
        "propertyId": triage_doc["propertyId"],
        "unitId": unit_id,
        "title": title,
        "description": decision.get("description") or "",
        "category": category,
        "priority": "urgent" if severity["tier"] in ("emergency", "urgent") else "normal",
        "source": "resident",
    }
    ticket_result = await create_ticket_document(ticket_doc)

    await sms_triage_col.update_one(
        {"_id": triage_doc["_id"]},
        {"$set": {"turns": turns, "concluded": True, "ticketId": ticket_result.get("id")}},
    )

    if ticket_result.get("wasExistingDuplicate"):
        response.message(f"Looks like you already have an open request for this: {title}. We're on it.")
    else:
        response.message(f"Thanks - logged as: {title}. We'll follow up soon. Reply anytime with an update.")

    return Response(content=str(response), media_type="application/xml")
