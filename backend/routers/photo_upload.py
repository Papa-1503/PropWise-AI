"""
Photo upload via a real, single-purpose link - the piece explicitly
deferred when the AI phone-triage and two-way SMS features were built
("creates the ticket with photos via SMS link" from the original
pitch). A resident who reports an issue by phone or text often has a
photo that would genuinely help a tech - this gives them a real way
to send one without needing an app login, the same "no login required"
principle already established for vendor_acceptance.py's tokenized
SLA links.

GET  /api/photo-upload/{token}   -> public - real ticket context (title,
                                      building, unit) for the upload
                                      page to show, or an honest
                                      "invalid or expired" if the
                                      token doesn't resolve
POST /api/photo-upload/{token}   -> public - uploads one photo, attaches
                                      its real Cloudinary URL to the
                                      ticket's photos array

create_upload_token() below is called internally by routers/sms_inbound.py
and routers/telephony.py right after they create a ticket via SMS/voice
triage - not itself an HTTP endpoint, just the real, shared token-
issuing logic both callers use identically.

Tokens expire via a real MongoDB TTL index on photo_upload_tokens_col
(see db.py's ensure_indexes) - once expired, the token document is
gone entirely, and both endpoints below treat "not found" as the
single honest answer for both "invalid" and "expired," since there's
no meaningful difference to the resident either way.
"""
import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, UploadFile, File
from bson import ObjectId
import cloudinary
import cloudinary.uploader

from db import photo_upload_tokens_col, tickets_col, properties_col

router = APIRouter(prefix="/api/photo-upload", tags=["photo-upload"])

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True,
)

TOKEN_EXPIRY_HOURS = 48


async def create_upload_token(ticket_id: str, property_id: str, unit_id: str) -> str:
    """Real, cryptographically random token (not a guessable sequence
    like an incrementing ID) - this is the only thing gating access to
    an otherwise-public endpoint, so it needs genuine unpredictability,
    not just uniqueness."""
    token = secrets.token_urlsafe(24)
    now = datetime.now(timezone.utc)
    await photo_upload_tokens_col.insert_one({
        "token": token,
        "ticketId": ticket_id,
        "propertyId": property_id,
        "unitId": unit_id,
        "createdAt": now,
        "expiresAt": now + timedelta(hours=TOKEN_EXPIRY_HOURS),
    })
    return token


@router.get("/{token}")
async def get_upload_context(token: str):
    token_doc = await photo_upload_tokens_col.find_one({"token": token})
    if not token_doc:
        raise HTTPException(status_code=404, detail="This link is invalid or has expired.")

    ticket = None
    if ObjectId.is_valid(token_doc["ticketId"]):
        ticket = await tickets_col.find_one({"_id": ObjectId(token_doc["ticketId"])})

    property_doc = None
    if ObjectId.is_valid(token_doc["propertyId"]):
        property_doc = await properties_col.find_one({"_id": ObjectId(token_doc["propertyId"])})
    elif token_doc.get("propertyId"):
        property_doc = await properties_col.find_one({"_id": token_doc["propertyId"]})

    return {
        "ticketTitle": ticket.get("title") if ticket else "Your maintenance request",
        "propertyName": property_doc.get("name") if property_doc else None,
        "unitId": token_doc.get("unitId"),
        "photoCount": len((ticket or {}).get("photos", [])),
    }


@router.post("/{token}")
async def upload_photo(token: str, file: UploadFile = File(...)):
    token_doc = await photo_upload_tokens_col.find_one({"token": token})
    if not token_doc:
        raise HTTPException(status_code=404, detail="This link is invalid or has expired.")

    content_type = file.content_type or ""
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Please upload a photo (JPG, PNG, etc).")

    file.file.seek(0)
    upload_result = cloudinary.uploader.upload(
        file.file, folder="rentflow/ticket-photos", resource_type="image",
    )
    photo_url = upload_result["secure_url"]

    if ObjectId.is_valid(token_doc["ticketId"]):
        await tickets_col.update_one(
            {"_id": ObjectId(token_doc["ticketId"])},
            {"$push": {"photos": photo_url}},
        )

    return {"uploaded": True, "photoUrl": photo_url}
