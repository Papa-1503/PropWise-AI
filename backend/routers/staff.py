"""
Staff management endpoints.

GET   /api/staff                          -> list staff users, with their property assignments
PATCH /api/staff/:id/properties            -> set which properties a staff member (e.g. a
                                              maintenance tech) is responsible for

Used to power auto-assignment of resident-submitted maintenance requests
to the right tech for that building (see routers/maintenance.py).
"""
from fastapi import APIRouter, HTTPException, Depends
from bson import ObjectId

from db import users_col
from models import StaffPropertyAssignment, StaffPhoneUpdate
from auth import require_staff
from audit_service import log_action

router = APIRouter(prefix="/api/staff", tags=["staff"])


def serialize(user: dict) -> dict:
    user["id"] = str(user.pop("_id"))
    user.pop("password", None)
    return user


@router.get("")
async def list_staff(user: dict = Depends(require_staff)):
    cursor = users_col.find({"role": "staff"})
    staff = await cursor.to_list(length=200)
    return {"staff": [serialize(s) for s in staff]}


@router.patch("/{user_id}/properties")
async def set_staff_properties(user_id: str, payload: StaffPropertyAssignment, user: dict = Depends(require_staff)):
    if not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=400, detail="Invalid user ID")

    result = await users_col.find_one_and_update(
        {"_id": ObjectId(user_id), "role": "staff"},
        {"$set": {"assignedProperties": payload.assignedProperties}},
        return_document=True,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Staff user not found")

    await log_action(
        actor_id=str(user["id"]), actor_email=user.get("email", ""),
        action="staff_properties_assigned", target_type="user", target_id=user_id,
        details={"assignedProperties": payload.assignedProperties},
    )

    return serialize(result)


@router.patch("/{user_id}/phone")
async def set_staff_phone(user_id: str, payload: StaffPhoneUpdate, user: dict = Depends(require_staff)):
    """Needed for on-call rotation to actually be contactable - a shift
    assigns a staff member as on-call, but that's only useful if there's
    a real number to reach them at. Any staff member can update this for
    themselves or, since this only requires require_staff (not a self-
    check), a manager can set it on someone else's behalf too - e.g.
    onboarding a new tech who hasn't logged in yet."""
    if not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=400, detail="Invalid user ID")

    result = await users_col.find_one_and_update(
        {"_id": ObjectId(user_id), "role": "staff"},
        {"$set": {"phone": payload.phone}},
        return_document=True,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Staff user not found")
    return serialize(result)
