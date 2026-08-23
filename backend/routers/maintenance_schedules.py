"""
Preventive maintenance schedule endpoints.

GET    /api/maintenance-schedules              -> list, filterable by propertyId
POST   /api/maintenance-schedules              -> create a recurring schedule
PATCH  /api/maintenance-schedules/:id          -> update a schedule

A schedule defines a recurring maintenance task (e.g. "HVAC filter check
every 90 days") for a property (or a specific unit). The actual "check
what's due and create tickets" logic lives separately (see the daily
check endpoint added in a later step) — this router is just CRUD for
defining what the recurring tasks are.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends
from bson import ObjectId

from db import maintenance_schedules_col
from date_utils import parse_date_utc
from models import MaintenanceScheduleCreate, MaintenanceScheduleUpdate
from auth import require_staff

router = APIRouter(prefix="/api/maintenance-schedules", tags=["maintenance-schedules"])


def serialize(schedule: dict) -> dict:
    schedule["id"] = str(schedule.pop("_id"))
    for field in ("nextDueDate", "lastCompletedDate", "createdAt"):
        if isinstance(schedule.get(field), datetime):
            schedule[field] = schedule[field].isoformat()
    return schedule


@router.get("")
async def list_schedules(propertyId: str | None = None, user: dict = Depends(require_staff)):
    query = {"propertyId": propertyId} if propertyId else {}
    cursor = maintenance_schedules_col.find(query).sort("nextDueDate", 1)
    schedules = await cursor.to_list(length=500)
    return {"schedules": [serialize(s) for s in schedules]}


@router.post("")
async def create_schedule(payload: MaintenanceScheduleCreate, user: dict = Depends(require_staff)):
    doc = payload.model_dump()
    doc["nextDueDate"] = parse_date_utc(doc["nextDueDate"])
    doc["lastCompletedDate"] = None
    doc["active"] = True
    doc["createdAt"] = datetime.now(timezone.utc)
    result = await maintenance_schedules_col.insert_one(doc)
    doc["_id"] = result.inserted_id
    return serialize(doc)


@router.patch("/{schedule_id}")
async def update_schedule(schedule_id: str, payload: MaintenanceScheduleUpdate, user: dict = Depends(require_staff)):
    if not ObjectId.is_valid(schedule_id):
        raise HTTPException(status_code=400, detail="Invalid schedule ID")
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    if "nextDueDate" in updates:
        updates["nextDueDate"] = parse_date_utc(updates["nextDueDate"])
    result = await maintenance_schedules_col.find_one_and_update(
        {"_id": ObjectId(schedule_id)}, {"$set": updates}, return_document=True
    )
    if not result:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return serialize(result)
