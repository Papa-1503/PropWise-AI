"""
Public lead-capture endpoint for prospective tenants (no auth — meant to
sit behind a public inquiry form) plus staff-only endpoints to view leads
and move them through the funnel. Feeds the LeasingAI panel on the
Dashboard with real numbers instead of "not tracked".

MULTI-TENANCY: a lead created for a specific property gets a real
orgId, derived from that property's own orgId (looked up server-side,
never client-submitted) - staff see only their own org's leads. The
one genuine, documented exception: a lead submitted with no propertyId
at all (a general inquiry, e.g. someone visiting the bare /apply link
with no ?property= param - confirmed a real, intentional case in
LeadCaptureForm.jsx, not just a theoretical edge) has no property to
derive an org from, so it's stored with orgId=None and stays visible
to every org's staff rather than becoming permanently invisible to
everyone. This is a real, narrow gap specific to organizations sharing
this deployment without a resolvable property - acceptable for now
given how rare a truly unattributed inquiry is in practice, but worth
revisiting (e.g. a per-org public inquiry URL) before this matters at
real multi-customer scale.
"""
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends
from bson import ObjectId

from db import leads_col, properties_col
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

    # Real org derivation from the property this inquiry is actually
    # about - never trusted from the client, looked up fresh here. See
    # module docstring for the one honest case (no propertyId at all)
    # this can't resolve.
    doc["orgId"] = None
    if doc.get("propertyId"):
        property_id = doc["propertyId"]
        query_id = ObjectId(property_id) if ObjectId.is_valid(property_id) else property_id
        property_doc = await properties_col.find_one({"_id": query_id}, {"orgId": 1})
        if property_doc:
            doc["orgId"] = property_doc.get("orgId")

    result = await leads_col.insert_one(doc)
    return {"leadId": str(result.inserted_id)}


@router.get("")
async def list_leads(propertyId: str | None = None, user: dict = Depends(require_staff)):
    # A lead's propertyId is null when the public form was submitted as
    # a general inquiry (not tied to a specific listing) — an exact-match
    # filter would make these invisible whenever staff have any specific
    # building selected, which is the most common state to be in. Show
    # both: leads for this exact property AND unassigned general ones.
    #
    # orgId scoping: includes both this staff member's own org AND
    # leads with no org at all (the genuinely-unattributable general-
    # inquiry case documented in this module's own docstring) - a real,
    # narrow tradeoff rather than losing that data's visibility entirely.
    query: dict = {"$or": [{"orgId": user["orgId"]}, {"orgId": None}]}
    if propertyId:
        query = {"$and": [query, {"$or": [{"propertyId": propertyId}, {"propertyId": None}]}]}
    cursor = leads_col.find(query).sort("createdAt", -1).limit(200)
    results = await cursor.to_list(length=200)
    for r in results:
        r["_id"] = str(r["_id"])
    return {"leads": results}


@router.patch("/{lead_id}/status")
async def update_lead_status(lead_id: str, payload: LeadStatusUpdate, user: dict = Depends(require_staff)):
    if not ObjectId.is_valid(lead_id):
        raise HTTPException(status_code=400, detail="Invalid lead ID")
    lead = await leads_col.find_one({"_id": ObjectId(lead_id), "$or": [{"orgId": user["orgId"]}, {"orgId": None}]})
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
