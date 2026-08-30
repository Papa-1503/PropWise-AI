"""
On-call rotation scheduler.

GET    /api/on-call/shifts                 -> list shifts, filterable by propertyId
                                               and/or a date range, sorted chronologically
POST   /api/on-call/shifts                 -> create a shift (one staff member covering
                                               one or more properties for a time window)
PATCH  /api/on-call/shifts/:id             -> edit a shift (also how manual swaps/
                                               overrides work - just edit or delete +
                                               recreate the affected shift, no separate
                                               override concept needed)
DELETE /api/on-call/shifts/:id             -> remove a shift
GET    /api/on-call/current                -> "who's on call right now" for a given
                                               propertyId - the hot-path lookup this
                                               entire feature exists to answer, and what
                                               after-hours call routing (not yet built)
                                               will eventually call directly

Recurring rotations are modeled as multiple individual shifts rather than
a recurrence-rule engine - e.g. "4 techs rotating weekly across 10
properties" is created as one POST per tech per week, not one recurring
rule object. Simpler to reason about and query, and a manual swap is then
just a normal edit to one shift rather than needing special override
logic layered on top of a recurrence system.

NOTE ON PRIOR WORK: an earlier session described building this exact
feature (routers/oncall.py, routers/telephony.py, on_call_log collection,
Twilio Voice webhook handlers) but that work has zero trace anywhere in
this repo's git history on any branch - it was apparently never actually
committed. This is a real rebuild from scratch, not a resume, and
deliberately scoped smaller for a first real pass: shift CRUD plus the
current-on-call lookup only. Call recording/transcription, Twilio Voice
webhook routing, and a separate on_call_log collection for after-hours
call history are follow-on work once this foundation is confirmed
correct, not included here.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends
from bson import ObjectId

from db import on_call_shifts_col, users_col
from date_utils import parse_date_utc
from models import OnCallShiftCreate, OnCallShiftUpdate
from auth import require_staff
from audit_service import log_action

router = APIRouter(prefix="/api/on-call", tags=["on-call"])


def serialize(shift: dict) -> dict:
    shift = dict(shift)
    shift["id"] = str(shift.pop("_id"))
    for field in ("startTime", "endTime", "createdAt"):
        if isinstance(shift.get(field), datetime):
            shift[field] = shift[field].isoformat()
    return shift


async def _attach_staff_name(shift: dict) -> dict:
    """Enrich a serialized shift with the assigned staff member's name,
    so the frontend doesn't need a second round-trip per shift just to
    show who's covering it. Falls back gracefully if the user was
    deleted after the shift was created, rather than crashing the whole
    list on one bad reference."""
    if not ObjectId.is_valid(shift.get("userId", "")):
        shift["userName"] = None
        return shift
    staff_user = await users_col.find_one({"_id": ObjectId(shift["userId"])})
    shift["userName"] = staff_user.get("name") if staff_user else None
    return shift


@router.get("/shifts")
async def list_shifts(
    propertyId: str | None = None,
    startAfter: str | None = None,
    startBefore: str | None = None,
    user: dict = Depends(require_staff),
):
    query = {}
    if propertyId:
        query["propertyIds"] = propertyId
    if startAfter or startBefore:
        time_filter = {}
        if startAfter:
            time_filter["$gte"] = parse_date_utc(startAfter)
        if startBefore:
            time_filter["$lte"] = parse_date_utc(startBefore)
        query["startTime"] = time_filter

    cursor = on_call_shifts_col.find(query).sort("startTime", 1)
    shifts = await cursor.to_list(length=500)
    enriched = [await _attach_staff_name(serialize(s)) for s in shifts]
    return {"shifts": enriched}


@router.post("/shifts")
async def create_shift(payload: OnCallShiftCreate, user: dict = Depends(require_staff)):
    if not ObjectId.is_valid(payload.userId):
        raise HTTPException(status_code=400, detail="Invalid user ID")
    assigned_user = await users_col.find_one({"_id": ObjectId(payload.userId), "role": "staff"})
    if not assigned_user:
        raise HTTPException(status_code=404, detail="Staff user not found")

    doc = payload.model_dump()
    doc["startTime"] = parse_date_utc(doc["startTime"])
    doc["endTime"] = parse_date_utc(doc["endTime"])
    if doc["endTime"] <= doc["startTime"]:
        raise HTTPException(status_code=400, detail="endTime must be after startTime")
    doc["createdAt"] = datetime.now(timezone.utc)

    result = await on_call_shifts_col.insert_one(doc)
    doc["_id"] = result.inserted_id

    await log_action(
        actor_id=str(user["_id"]), actor_email=user.get("email", ""),
        action="on_call_shift_created", target_type="on_call_shift", target_id=str(result.inserted_id),
        details={"assignedUserId": payload.userId, "propertyIds": payload.propertyIds},
    )

    return await _attach_staff_name(serialize(doc))


@router.patch("/shifts/{shift_id}")
async def update_shift(shift_id: str, payload: OnCallShiftUpdate, user: dict = Depends(require_staff)):
    if not ObjectId.is_valid(shift_id):
        raise HTTPException(status_code=400, detail="Invalid shift ID")

    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    if "userId" in updates:
        if not ObjectId.is_valid(updates["userId"]):
            raise HTTPException(status_code=400, detail="Invalid user ID")
        assigned_user = await users_col.find_one({"_id": ObjectId(updates["userId"]), "role": "staff"})
        if not assigned_user:
            raise HTTPException(status_code=404, detail="Staff user not found")
    if "startTime" in updates:
        updates["startTime"] = parse_date_utc(updates["startTime"])
    if "endTime" in updates:
        updates["endTime"] = parse_date_utc(updates["endTime"])

    # If only one of start/end is being changed, still validate the
    # resulting pair makes sense rather than only checking the two
    # fields when both happen to be edited together.
    existing = await on_call_shifts_col.find_one({"_id": ObjectId(shift_id)})
    if not existing:
        raise HTTPException(status_code=404, detail="Shift not found")
    new_start = updates.get("startTime", existing["startTime"])
    new_end = updates.get("endTime", existing["endTime"])
    if new_end <= new_start:
        raise HTTPException(status_code=400, detail="endTime must be after startTime")

    result = await on_call_shifts_col.find_one_and_update(
        {"_id": ObjectId(shift_id)}, {"$set": updates}, return_document=True
    )
    return await _attach_staff_name(serialize(result))


@router.delete("/shifts/{shift_id}")
async def delete_shift(shift_id: str, user: dict = Depends(require_staff)):
    if not ObjectId.is_valid(shift_id):
        raise HTTPException(status_code=400, detail="Invalid shift ID")
    result = await on_call_shifts_col.delete_one({"_id": ObjectId(shift_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Shift not found")

    await log_action(
        actor_id=str(user["_id"]), actor_email=user.get("email", ""),
        action="on_call_shift_deleted", target_type="on_call_shift", target_id=shift_id,
    )

    return {"deleted": True}


@router.get("/current")
async def current_on_call(propertyId: str, user: dict = Depends(require_staff)):
    """Who's on call right now for a given property. This is the actual
    reason this feature exists - everything else (shift CRUD) is just
    the data entry needed to make this query answerable. Returns null
    (not a 404) when nobody's currently scheduled, since "nobody is on
    call right now" is a valid, expected state a manager needs to see
    and fix, not an error condition."""
    now = datetime.now(timezone.utc)
    shift = await on_call_shifts_col.find_one({
        "propertyIds": propertyId,
        "startTime": {"$lte": now},
        "endTime": {"$gte": now},
    })
    if not shift:
        return {"onCall": None}
    return {"onCall": await _attach_staff_name(serialize(shift))}
