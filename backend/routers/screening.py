"""
Tenant screening requests — background/credit check tracking.

No live screening provider is wired in yet. This is deliberately built as
a request/status pipeline that a real provider (e.g. TransUnion SmartMove,
Checkr) can plug into later: swap the body of create_screening_request to
call their API instead of just inserting a "pending" record, and have
their webhook/callback hit update_screening_status instead of a staff
member doing it manually. Nothing else in the app needs to change.

Screening reports involve consumer credit data protected by the FCRA —
do not connect this to a real provider or use it on real applicants
without the required business agreement and compliance paperwork in place.
"""
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends
from bson import ObjectId

from db import screening_col
from models import ScreeningRequestCreate, ScreeningStatusUpdate
from auth import require_staff

router = APIRouter(prefix="/api/screening", tags=["screening"])


def serialize(doc: dict) -> dict:
    doc["id"] = str(doc.pop("_id"))
    if isinstance(doc.get("createdAt"), datetime):
        doc["createdAt"] = doc["createdAt"].isoformat()
    if isinstance(doc.get("updatedAt"), datetime):
        doc["updatedAt"] = doc["updatedAt"].isoformat()
    return doc


@router.post("")
async def create_screening_request(payload: ScreeningRequestCreate, user: dict = Depends(require_staff)):
    doc = payload.model_dump()
    doc["status"] = "pending"
    doc["notes"] = None
    doc["createdAt"] = datetime.now(timezone.utc)
    result = await screening_col.insert_one(doc)
    doc["_id"] = result.inserted_id
    return serialize(doc)


@router.get("")
async def list_screening_requests(
    leadId: str | None = None,
    status: str | None = None,
    user: dict = Depends(require_staff),
):
    query = {}
    if leadId:
        query["leadId"] = leadId
    if status:
        query["status"] = status
    cursor = screening_col.find(query).sort("createdAt", -1).limit(200)
    results = await cursor.to_list(length=200)
    return {"screeningRequests": [serialize(r) for r in results]}


@router.get("/{screening_id}")
async def get_screening_request(screening_id: str, user: dict = Depends(require_staff)):
    if not ObjectId.is_valid(screening_id):
        raise HTTPException(status_code=400, detail="Invalid screening request ID")
    doc = await screening_col.find_one({"_id": ObjectId(screening_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Screening request not found")
    return serialize(doc)


@router.patch("/{screening_id}/status")
async def update_screening_status(screening_id: str, payload: ScreeningStatusUpdate, user: dict = Depends(require_staff)):
    if not ObjectId.is_valid(screening_id):
        raise HTTPException(status_code=400, detail="Invalid screening request ID")
    updates = {
        "status": payload.status,
        "updatedAt": datetime.now(timezone.utc),
    }
    if payload.notes is not None:
        updates["notes"] = payload.notes
    result = await screening_col.find_one_and_update(
        {"_id": ObjectId(screening_id)}, {"$set": updates}, return_document=True
    )
    if not result:
        raise HTTPException(status_code=404, detail="Screening request not found")
    return serialize(result)
