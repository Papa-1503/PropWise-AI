"""
Unified communication log endpoints.

GET  /api/communications?propertyId=&unitId=   -> merged timeline for a unit
POST /api/communications                       -> log a communication manually (a
                                                   phone call, an in-person chat —
                                                   anything that happened outside
                                                   the app)
POST /api/communications/send-email             -> actually sends an email (via the
                                                   existing SMTP email_service) and
                                                   logs it to the timeline
POST /api/communications/send-sms                -> same, via Twilio SMS
POST /api/communications/send-group              -> dynamic message grouping - sends
                                                   to every resident matching real
                                                   filters (property, occupancy
                                                   status, renewal status) at once,
                                                   rather than one unit at a time

Step 2 of the Communication Hub: real outbound email, reusing the
existing provider-agnostic SMTP email service rather than adding a
second, redundant email system. Inbound replies (a tenant emailing back
and it appearing here automatically) are deliberately deferred — that
needs an inbound webhook (e.g. SendGrid Inbound Parse) which requires
DNS changes and a public endpoint, out of scope for this step.

MULTI-TENANCY: every communication carries a real orgId, stamped
server-side from the creating staff member's own orgId - never client-
submitted. send-group additionally verifies the given propertyId
actually belongs to the caller's own org before sending anything - a
real, necessary check, not just defense in depth: propertyId values
are globally unique real IDs, so without this check a staff member
could have sent a real group message to a DIFFERENT organization's
residents simply by knowing (or guessing) their property ID.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from db import communications_col
from models import CommunicationCreate, SendEmailCommunication, SendSmsCommunication, GroupMessageSend
from auth import require_staff
from email_service import send_email_async, EmailNotConfigured, EmailSendError
from sms_service import send_sms_async, SmsNotConfigured, SmsSendError
from db import properties_col, leases_col
from bson import ObjectId

router = APIRouter(prefix="/api/communications", tags=["communications"])


def serialize(comm: dict) -> dict:
    comm["id"] = str(comm.pop("_id"))
    if isinstance(comm.get("createdAt"), datetime):
        comm["createdAt"] = comm["createdAt"].isoformat()
    return comm


@router.get("")
async def list_communications(propertyId: str | None = None, unitId: str | None = None, user: dict = Depends(require_staff)):
    query: dict = {"orgId": user["orgId"]}
    if propertyId:
        query["propertyId"] = propertyId
    if unitId:
        query["unitId"] = unitId
    cursor = communications_col.find(query).sort("createdAt", -1).limit(200)
    comms = await cursor.to_list(length=200)
    return {"communications": [serialize(c) for c in comms]}


@router.post("")
async def create_communication(payload: CommunicationCreate, user: dict = Depends(require_staff)):
    doc = payload.model_dump()
    doc["orgId"] = user["orgId"]
    doc["loggedBy"] = user.get("email")
    doc["createdAt"] = datetime.now(timezone.utc)
    result = await communications_col.insert_one(doc)
    doc["_id"] = result.inserted_id
    return serialize(doc)


@router.post("/send-email")
async def send_email_communication(payload: SendEmailCommunication, user: dict = Depends(require_staff)):
    doc = {
        "propertyId": payload.propertyId,
        "unitId": payload.unitId,
        "orgId": user["orgId"],
        "channel": "email",
        "direction": "outbound",
        "subject": payload.subject,
        "body": payload.body,
        "to": payload.to,
        "loggedBy": user.get("email"),
        "createdAt": datetime.now(timezone.utc),
    }

    try:
        await send_email_async(to=payload.to, subject=payload.subject, body_text=payload.body)
        doc["status"] = "sent"
    except (EmailNotConfigured, EmailSendError) as exc:
        doc["status"] = "failed"
        doc["error"] = str(exc)
        result = await communications_col.insert_one(doc)
        doc["_id"] = result.inserted_id
        # Still log the failed attempt (so staff can see it didn't go out),
        # but surface the error to the caller rather than pretending it worked.
        raise HTTPException(status_code=502, detail=f"Email failed to send: {exc}")

    result = await communications_col.insert_one(doc)
    doc["_id"] = result.inserted_id
    return serialize(doc)


@router.post("/send-sms")
async def send_sms_communication(payload: SendSmsCommunication, user: dict = Depends(require_staff)):
    doc = {
        "propertyId": payload.propertyId,
        "unitId": payload.unitId,
        "orgId": user["orgId"],
        "channel": "sms",
        "direction": "outbound",
        "body": payload.body,
        "to": payload.to,
        "loggedBy": user.get("email"),
        "createdAt": datetime.now(timezone.utc),
    }

    try:
        message_sid = await send_sms_async(to=payload.to, body=payload.body)
        doc["status"] = "sent"
        doc["providerMessageId"] = message_sid
    except (SmsNotConfigured, SmsSendError) as exc:
        doc["status"] = "failed"
        doc["error"] = str(exc)
        result = await communications_col.insert_one(doc)
        doc["_id"] = result.inserted_id
        # Same honest pattern as send-email — log the failed attempt so
        # staff can see it didn't go out, but still surface the real
        # error to the caller rather than pretending it worked.
        raise HTTPException(status_code=502, detail=f"SMS failed to send: {exc}")

    result = await communications_col.insert_one(doc)
    doc["_id"] = result.inserted_id
    return serialize(doc)


@router.post("/send-group")
async def send_group_message(payload: GroupMessageSend, user: dict = Depends(require_staff)):
    """Dynamic message grouping — sends to every resident matching the
    given filters at once, instead of one unit at a time. Real group
    targets only: propertyId (a building) and/or occupancyStatus/
    renewalStatus (real, already-stored fields) — see GroupMessageSend's
    docstring in models.py for why floor was deliberately left out
    rather than faked from an unreliable unit-numbering assumption.

    Resolves recipients from leases_col (email or phone, depending on
    channel), cross-referencing properties_col.units when
    occupancyStatus is given, since that field lives on the property's
    embedded unit list, not on the lease itself.

    Sends to each recipient independently and never lets one failure
    abort the batch — same resilience pattern as
    admin.py's run_autopay_check: attempt every recipient, collect
    real per-recipient outcomes, return an honest summary rather than
    an all-or-nothing result. A resident with a malformed or missing
    contact field is skipped and reported, not silently dropped or
    allowed to fail the whole send.

    Real ownership check, not just scoping: propertyId is verified to
    belong to the caller's own org BEFORE any lease is queried or any
    message is sent - without this, a staff member could send a real
    group message to a different organization's residents simply by
    supplying that org's real property ID."""
    if payload.channel == "email" and not payload.subject:
        raise HTTPException(status_code=400, detail="subject is required for email group messages.")

    property_query_id = ObjectId(payload.propertyId) if ObjectId.is_valid(payload.propertyId) else payload.propertyId
    property_doc = await properties_col.find_one({"_id": property_query_id, "orgId": user["orgId"]})
    if not property_doc:
        raise HTTPException(status_code=404, detail="Property not found")

    lease_query: dict = {"propertyId": payload.propertyId, "orgId": user["orgId"]}
    if payload.renewalStatus:
        lease_query["renewalStatus"] = payload.renewalStatus
    leases = await leases_col.find(lease_query).to_list(length=1000)

    if payload.occupancyStatus:
        matching_unit_ids = {
            u["unitId"] for u in property_doc.get("units", [])
            if u.get("status") == payload.occupancyStatus
        }
        leases = [l for l in leases if l.get("unitId") in matching_unit_ids]

    sent = []
    failed = []
    skipped_no_contact = []

    for lease in leases:
        unit_id = lease.get("unitId")
        contact = lease.get("residentEmail") if payload.channel == "email" else lease.get("residentPhone")
        if not contact:
            skipped_no_contact.append(unit_id)
            continue

        doc = {
            "propertyId": payload.propertyId,
            "unitId": unit_id,
            "orgId": user["orgId"],
            "channel": payload.channel,
            "direction": "outbound",
            "subject": payload.subject if payload.channel == "email" else None,
            "body": payload.body,
            "to": contact,
            "loggedBy": user.get("email"),
            "createdAt": datetime.now(timezone.utc),
            "groupSend": True,
        }

        try:
            if payload.channel == "email":
                await send_email_async(to=contact, subject=payload.subject, body_text=payload.body)
            else:
                await send_sms_async(to=contact, body=payload.body)
            doc["status"] = "sent"
            sent.append(unit_id)
        except (EmailNotConfigured, EmailSendError, SmsNotConfigured, SmsSendError) as exc:
            doc["status"] = "failed"
            doc["error"] = str(exc)
            failed.append({"unitId": unit_id, "error": str(exc)})

        await communications_col.insert_one(doc)

    return {
        "status": "done",
        "recipientsMatched": len(leases),
        "sent": len(sent),
        "failed": len(failed),
        "skippedNoContact": len(skipped_no_contact),
        "sentUnitIds": sent,
        "failedDetails": failed,
        "skippedUnitIds": skipped_no_contact,
    }
