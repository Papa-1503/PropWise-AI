"""
Public lead-capture endpoint for prospective tenants (no auth — meant to
sit behind a public inquiry form) plus staff-only endpoints to view leads
and move them through the funnel. Feeds the LeasingAI panel on the
Dashboard with real numbers instead of "not tracked".
"""
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends
from bson import ObjectId

from db import leads_col
from models import LeadCreate, LeadStatusUpdate
from auth import require_staff

router = APIRouter(prefix="/api/leads", tags=["leads"])


@router.post("")
async def create_lead(payload: LeadCreate):
    doc = payload.model_dump()
    doc["status"] = "new"
    doc["createdAt"] = datetime.now(timezone.utc)
    doc["touredAt"] = None
    doc["appliedAt"] = None
    doc["signedAt"] = None
    result = await leads_col.insert_one(doc)
    return {"leadId": str(result.inserted_id)}


@router.get("")
async def list_leads(propertyId: str | None = None, user: dict = Depends(require_staff)):
    # A lead's propertyId is null when the public form was submitted as
    # a general inquiry (not tied to a specific listing) — an exact-match
    # filter would make these invisible whenever staff have any specific
    # building selected, which is the most common state to be in. Show
    # both: leads for this exact property AND unassigned general ones.
    query = {"$or": [{"propertyId": propertyId}, {"propertyId": None}]} if propertyId else {}
    cursor = leads_col.find(query).sort("createdAt", -1).limit(200)
    results = await cursor.to_list(length=200)
    for r in results:
        r["_id"] = str(r["_id"])
    return {"leads": results}


@router.patch("/{lead_id}/status")
async def update_lead_status(lead_id: str, payload: LeadStatusUpdate, user: dict = Depends(require_staff)):
    if not ObjectId.is_valid(lead_id):
        raise HTTPException(status_code=400, detail="Invalid lead ID")
    lead = await leads_col.find_one({"_id": ObjectId(lead_id)})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    now = datetime.now(timezone.utc)
    update = {"status": payload.status}
    if payload.status == "toured" and not lead.get("touredAt"):
        update["touredAt"] = now
    if payload.status == "applied" and not lead.get("appliedAt"):
        update["appliedAt"] = now
    if payload.status == "signed" and not lead.get("signedAt"):
        update["signedAt"] = now

    await leads_col.update_one({"_id": ObjectId(lead_id)}, {"$set": update})
    return {"status": "updated"}
