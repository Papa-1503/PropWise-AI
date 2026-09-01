"""
Tour scheduling — self-guided/virtual showing booking.

    POST   /api/tours/slots                          -> staff creates an available slot
    GET    /api/tours/slots?propertyId=&unitId=        -> PUBLIC: list open, future slots with room left
    POST   /api/tours/slots/{slot_id}/book             -> PUBLIC: book a slot (no auth — matches
                                                           create_lead's existing public pattern)
    GET    /api/tours/bookings?propertyId=&slotId=      -> staff views bookings
    DELETE /api/tours/slots/{slot_id}                  -> staff removes an unused slot

Genuinely missing before this: leads.py only ever recorded THAT a tour
happened after the fact (a touredAt timestamp) — nothing let a prospect
actually book one. Self-service by design, matching the public,
no-auth pattern already used by POST /api/leads.

The one thing that has to be airtight here: capacity can never be
exceeded, even if two people book the same last slot at the same
moment. That's enforced with a single atomic Mongo update
(find_one_and_update with a bookedCount < capacity filter baked into
the query itself) — not a read-then-write, which would have a real
race condition window between the two steps.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends
from bson import ObjectId

from db import tour_slots_col, tour_bookings_col, leads_col
from models import TourSlotCreate, TourBookingCreate
from date_utils import parse_date_utc
from auth import require_staff
import notifications_service

router = APIRouter(prefix="/api/tours", tags=["tours"])


def serialize(doc: dict) -> dict:
    doc["id"] = str(doc.pop("_id"))
    for field in ("startTime", "endTime", "createdAt", "bookedAt"):
        if isinstance(doc.get(field), datetime):
            doc[field] = doc[field].isoformat()
    return doc


@router.post("/slots")
async def create_slot(payload: TourSlotCreate, user: dict = Depends(require_staff)):
    doc = payload.model_dump()
    doc["startTime"] = parse_date_utc(doc["startTime"])
    doc["endTime"] = parse_date_utc(doc["endTime"])
    if doc["endTime"] <= doc["startTime"]:
        raise HTTPException(status_code=400, detail="endTime must be after startTime")
    doc["bookedCount"] = 0
    doc["createdAt"] = datetime.now(timezone.utc)
    result = await tour_slots_col.insert_one(doc)
    doc["_id"] = result.inserted_id
    return serialize(doc)


@router.get("/slots")
async def list_open_slots(propertyId: str, unitId: str | None = None):
    """PUBLIC — no auth. Only shows slots that are still in the future
    and genuinely have room left (bookedCount < capacity) — a prospect
    should never see a slot they can't actually book."""
    now = datetime.now(timezone.utc)
    query: dict = {"propertyId": propertyId, "startTime": {"$gt": now}}
    if unitId:
        query["unitId"] = unitId
    cursor = tour_slots_col.find(query).sort("startTime", 1).limit(200)
    slots = await cursor.to_list(length=200)
    open_slots = [s for s in slots if s.get("bookedCount", 0) < s.get("capacity", 1)]
    return {"slots": [serialize(s) for s in open_slots]}


@router.post("/slots/{slot_id}/book")
async def book_slot(slot_id: str, payload: TourBookingCreate):
    """PUBLIC — no auth. Atomically reserves one spot: the $lt filter is
    evaluated as part of the SAME update operation that increments
    bookedCount, so two simultaneous requests for the last spot cannot
    both succeed — MongoDB serializes writes to a single document, so
    only one of them will match the filter and actually increment."""
    if not ObjectId.is_valid(slot_id):
        raise HTTPException(status_code=400, detail="Invalid slot ID")

    slot = await tour_slots_col.find_one({"_id": ObjectId(slot_id)})
    if not slot:
        raise HTTPException(status_code=404, detail="Tour slot not found")
    if slot["startTime"] <= datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="This slot has already passed")

    reserved = await tour_slots_col.find_one_and_update(
        {"_id": ObjectId(slot_id), "$expr": {"$lt": ["$bookedCount", "$capacity"]}},
        {"$inc": {"bookedCount": 1}},
        return_document=True,
    )
    if not reserved:
        raise HTTPException(status_code=409, detail="This slot just filled up — please pick another time.")

    # Auto-create (or link to an existing) lead so a booked tour feeds
    # the real leads pipeline rather than living in a separate system.
    lead = await leads_col.find_one({"email": payload.email, "propertyId": slot["propertyId"]})
    if not lead:
        lead_doc = {
            "name": payload.name, "email": payload.email, "phone": payload.phone,
            "propertyId": slot["propertyId"], "unitId": slot.get("unitId"),
            "message": f"Booked a tour for {slot['startTime'].isoformat()}",
            "status": "new", "touredAt": None, "createdAt": datetime.now(timezone.utc),
        }
        lead_result = await leads_col.insert_one(lead_doc)
        lead_id = str(lead_result.inserted_id)
    else:
        lead_id = str(lead["_id"])

    booking_doc = {
        "slotId": slot_id, "propertyId": slot["propertyId"], "unitId": slot.get("unitId"),
        "name": payload.name, "email": payload.email, "phone": payload.phone,
        "leadId": lead_id, "bookedAt": datetime.now(timezone.utc),
    }
    result = await tour_bookings_col.insert_one(booking_doc)
    booking_doc["_id"] = result.inserted_id

    await notifications_service.notify_all_staff(
        type="general",
        title="New tour booked",
        body=f"{payload.name} booked a tour for {slot['startTime'].strftime('%b %d, %Y %I:%M %p')}",
        link=f"/tours/bookings/{str(result.inserted_id)}",
    )

    return serialize(booking_doc)


@router.get("/bookings")
async def list_bookings(propertyId: str | None = None, slotId: str | None = None, user: dict = Depends(require_staff)):
    query: dict = {}
    if propertyId:
        query["propertyId"] = propertyId
    if slotId:
        query["slotId"] = slotId
    cursor = tour_bookings_col.find(query).sort([("bookedAt", -1), ("_id", -1)]).limit(500)
    bookings = await cursor.to_list(length=500)
    return {"bookings": [serialize(b) for b in bookings]}


@router.delete("/slots/{slot_id}")
async def delete_slot(slot_id: str, user: dict = Depends(require_staff)):
    if not ObjectId.is_valid(slot_id):
        raise HTTPException(status_code=400, detail="Invalid slot ID")
    slot = await tour_slots_col.find_one({"_id": ObjectId(slot_id)})
    if not slot:
        raise HTTPException(status_code=404, detail="Tour slot not found")
    if slot.get("bookedCount", 0) > 0:
        raise HTTPException(status_code=400, detail="Can't delete a slot with existing bookings — cancel the bookings first.")
    await tour_slots_col.delete_one({"_id": ObjectId(slot_id)})
    return {"deleted": True}
