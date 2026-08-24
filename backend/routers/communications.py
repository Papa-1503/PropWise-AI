"""
Unified communication log endpoints.

GET  /api/communications?propertyId=&unitId=   -> merged timeline for a unit
POST /api/communications                       -> log a communication (staff-entered
                                                   for now; real SMS/email sending via
                                                   Twilio/SendGrid comes in a later step
                                                   and will call this same insert path)

This is Step 1 of the Communication Hub: the data model and a way to see
one merged timeline per unit, regardless of channel. It doesn't send
anything yet — staff can log what happened (a call, an email sent
outside the app) so there's a real record to build the automated
sending on top of later, without waiting on Twilio/SendGrid setup first.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from db import communications_col
from models import CommunicationCreate
from auth import require_staff

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
