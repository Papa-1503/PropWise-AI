"""
Lease endpoints.

GET   /api/leases?propertyId=&expiringWithinDays=   -> list, optionally filtered
POST  /api/leases                                   -> create a lease
PATCH /api/leases/:id                                -> update renewal status / balance
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Depends
from bson import ObjectId

from db import leases_col
from models import LeaseCreate, LeaseUpdate
from date_utils import parse_date_utc
from auth import require_staff

router = APIRouter(prefix="/api/leases", tags=["leases"])


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
    doc["createdAt"] = datetime.now(timezone.utc)
    result = await leases_col.insert_one(doc)
    doc["_id"] = result.inserted_id
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
