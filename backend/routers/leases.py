"""
Lease endpoints.

GET   /api/leases?propertyId=&expiringWithinDays=   -> list, optionally filtered
POST  /api/leases                                   -> create a lease
PATCH /api/leases/:id                                -> update renewal status / balance
"""
from datetime import datetime, timedelta, timezone
import secrets
import string

from fastapi import APIRouter, HTTPException, Depends
from bson import ObjectId

from db import leases_col, documents_col
from models import LeaseCreate, LeaseUpdate
from date_utils import parse_date_utc
from auth import require_staff
from services.events import emit_event
router = APIRouter(prefix="/api/leases", tags=["leases"])

# Excludes visually ambiguous characters (0/O, 1/I/l) so a resident can
# type the code correctly from a printed/texted invite without confusion.
_INVITE_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def generate_invite_code() -> str:
    return "".join(secrets.choice(_INVITE_CODE_ALPHABET) for _ in range(8))



def serialize(lease: dict) -> dict:
    lease["id"] = str(lease.pop("_id"))
    for field in ("startDate", "endDate"):
        if isinstance(lease.get(field), datetime):
            lease[field] = lease[field].isoformat()
    return lease


@router.get("")
async def list_leases(propertyId: str | None = None, expiringWithinDays: int | None = None, user: dict = Depends(require_staff)):
    query: dict = {}
    if propertyId:
        query["propertyId"] = propertyId
    if expiringWithinDays is not None:
        cutoff = datetime.now(timezone.utc) + timedelta(days=expiringWithinDays)
        query["endDate"] = {"$lte": cutoff}
    cursor = leases_col.find(query).sort("endDate", 1)
    leases = await cursor.to_list(length=500)
    return {"leases": [serialize(l) for l in leases]}


@router.post("")
async def create_lease(payload: LeaseCreate, user: dict = Depends(require_staff)):
    doc = payload.model_dump()
    doc["startDate"] = parse_date_utc(doc["startDate"])
    doc["endDate"] = parse_date_utc(doc["endDate"])
    doc["balance"] = 0
    doc["inviteCode"] = generate_invite_code()
    doc["createdAt"] = datetime.now(timezone.utc)
    result = await leases_col.insert_one(doc)
    doc["_id"] = result.inserted_id

    try:
        await emit_event("lease_created", {
            "leaseId": str(result.inserted_id),
            "propertyId": doc.get("propertyId"),
            "unitId": doc.get("unitId"),
            "residentEmail": doc.get("residentEmail"),
            "residentName": doc.get("residentName"),
        })
    except Exception as e:
        print(f"Workflow dispatch failed: {e}")

    return serialize(doc)


@router.patch("/{lease_id}")
async def update_lease(lease_id: str, payload: LeaseUpdate, user: dict = Depends(require_staff)):
    if not ObjectId.is_valid(lease_id):
        raise HTTPException(status_code=400, detail="Invalid lease ID")
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    if "endDate" in updates:
        updates["endDate"] = parse_date_utc(updates["endDate"])
    result = await leases_col.find_one_and_update(
        {"_id": ObjectId(lease_id)}, {"$set": updates}, return_document=True
    )
    if not result:
        raise HTTPException(status_code=404, detail="Lease not found")
    return serialize(result)

@router.post("/{lease_id}/generate-document")
async def generate_lease_document(lease_id: str, user: dict = Depends(require_staff)):
    if not ObjectId.is_valid(lease_id):
        raise HTTPException(status_code=400, detail="Invalid lease ID")
    lease = await leases_col.find_one({"_id": ObjectId(lease_id)})
    if not lease:
        raise HTTPException(status_code=404, detail="Lease not found")

    # Idempotency: if an unsigned document already exists for this lease,
    # return it instead of creating another one. Without this, clicking
    # "Generate document" more than once (easy to do — no visible sign
    # a document already exists) silently creates duplicate pending
    # documents, which would confuse a tenant seeing multiple "please
    # sign" requests for the same lease.
    existing = await documents_col.find_one({"leaseId": lease_id, "status": "pending"})
    if existing:
        return {"documentId": str(existing["_id"]), "alreadyExisted": True}

    if not lease.get("residentEmail"):
        raise HTTPException(status_code=400, detail="Lease has no resident email on file")

    start = lease.get("startDate")
    end = lease.get("endDate")
    start_str = start.strftime("%B %d, %Y") if isinstance(start, datetime) else str(start)
    end_str = end.strftime("%B %d, %Y") if isinstance(end, datetime) else str(end)

    content = (
        f"This lease agreement is between the property and {lease.get('residentName', 'the resident')} "
        f"for unit {lease.get('unitId')}.\n\n"
        f"Lease term: {start_str} through {end_str}.\n\n"
        f"Monthly rent: ${lease.get('rent', 0):,.2f}.\n\n"
        f"By signing below, the resident acknowledges agreement to the terms above. "
        f"This document was generated from lease record {lease_id}."
    )

    doc = {
        "tenantEmail": lease["residentEmail"],
        "leaseId": lease_id,
        "title": f"Lease Agreement - Unit {lease.get('unitId')}",
        "content": content,
        "status": "pending",
        "signedByName": None,
        "signedAt": None,
        "createdAt": datetime.now(timezone.utc),
    }
    result = await documents_col.insert_one(doc)
    return {"documentId": str(result.inserted_id), "alreadyExisted": False}
 
