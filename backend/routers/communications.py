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

Step 2 of the Communication Hub: real outbound email, reusing the
existing provider-agnostic SMTP email service rather than adding a
second, redundant email system. Inbound replies (a tenant emailing back
and it appearing here automatically) are deliberately deferred — that
needs an inbound webhook (e.g. SendGrid Inbound Parse) which requires
DNS changes and a public endpoint, out of scope for this step.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from db import communications_col
from models import CommunicationCreate, SendEmailCommunication
from auth import require_staff
from email_service import send_email_async, EmailNotConfigured, EmailSendError

router = APIRouter(prefix="/api/communications", tags=["communications"])


def serialize(comm: dict) -> dict:
    comm["id"] = str(comm.pop("_id"))
    if isinstance(comm.get("createdAt"), datetime):
        comm["createdAt"] = comm["createdAt"].isoformat()
    return comm


@router.get("")
async def list_communications(propertyId: str | None = None, unitId: str | None = None, user: dict = Depends(require_staff)):
    query = {}
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
