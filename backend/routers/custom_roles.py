"""
Custom roles & permissions (P18).

GET/POST   /api/custom-roles                       -> role CRUD
PATCH      /api/custom-roles/{id}
DELETE     /api/custom-roles/{id}
PATCH      /api/custom-roles/staff/{userId}/assign  -> assign (or clear, via
                                                        customRoleId: null) a
                                                        staff member's custom
                                                        role

Genuinely additive to the existing role system - see
require_permission's docstring in auth.py, and CustomRoleCreate's
docstring in models.py, for the full reasoning on why this doesn't
touch any of the 177 existing require_staff-protected endpoints. A
staff member with no custom role assigned keeps today's real default
behavior (full access); assigning one scopes them to exactly that
role's real permission list, checked only by NEW endpoints that
explicitly opt into require_permission going forward.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends
from bson import ObjectId

from db import custom_roles_col, users_col
from models import CustomRoleCreate, CustomRoleUpdate, StaffCustomRoleAssign
from auth import require_staff
from audit_service import log_action

router = APIRouter(prefix="/api/custom-roles", tags=["custom-roles"])


def serialize(doc: dict) -> dict:
    doc = dict(doc)
    doc["id"] = str(doc.pop("_id"))
    return doc


@router.post("")
async def create_custom_role(payload: CustomRoleCreate, user: dict = Depends(require_staff)):
    doc = payload.model_dump()
    doc["createdAt"] = datetime.now(timezone.utc)
    result = await custom_roles_col.insert_one(doc)
    doc["_id"] = result.inserted_id

    await log_action(
        actor_id=str(user["_id"]), actor_email=user.get("email", ""),
        action="custom_role_created", target_type="custom_role", target_id=str(result.inserted_id),
        details={"name": payload.name, "permissions": payload.permissions},
    )

    return serialize(doc)


@router.get("")
async def list_custom_roles(user: dict = Depends(require_staff)):
    roles = await custom_roles_col.find({}).sort("name", 1).to_list(length=200)
    return {"roles": [serialize(r) for r in roles]}


@router.patch("/{role_id}")
async def update_custom_role(role_id: str, payload: CustomRoleUpdate, user: dict = Depends(require_staff)):
    if not ObjectId.is_valid(role_id):
        raise HTTPException(status_code=400, detail="Invalid role ID")
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    result = await custom_roles_col.find_one_and_update(
        {"_id": ObjectId(role_id)}, {"$set": updates}, return_document=True
    )
    if not result:
        raise HTTPException(status_code=404, detail="Role not found")

    await log_action(
        actor_id=str(user["_id"]), actor_email=user.get("email", ""),
        action="custom_role_updated", target_type="custom_role", target_id=role_id,
        details=updates,
    )

    return serialize(result)


@router.delete("/{role_id}")
async def delete_custom_role(role_id: str, user: dict = Depends(require_staff)):
    """Real, deliberate safety check: refuses to delete a role that's
    still assigned to at least one staff member, rather than silently
    deleting it and leaving those accounts referencing a customRoleId
    that no longer exists - require_permission's own fallback (a
    malformed/missing role doc grants full access, so a dangling
    reference wouldn't lock anyone out) makes this non-catastrophic
    even if it happened, but a deliberate block here is more honest
    than relying on that fallback to paper over a real data
    inconsistency."""
    if not ObjectId.is_valid(role_id):
        raise HTTPException(status_code=400, detail="Invalid role ID")
    still_assigned = await users_col.count_documents({"customRoleId": role_id})
    if still_assigned > 0:
        raise HTTPException(
            status_code=400,
            detail=f"This role is still assigned to {still_assigned} staff member(s). Reassign them first.",
        )
    result = await custom_roles_col.delete_one({"_id": ObjectId(role_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Role not found")

    await log_action(
        actor_id=str(user["_id"]), actor_email=user.get("email", ""),
        action="custom_role_deleted", target_type="custom_role", target_id=role_id,
    )

    return {"deleted": True}


@router.patch("/staff/{user_id}/assign")
async def assign_custom_role(user_id: str, payload: StaffCustomRoleAssign, user: dict = Depends(require_staff)):
    if not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=400, detail="Invalid user ID")
    if payload.customRoleId and not ObjectId.is_valid(payload.customRoleId):
        raise HTTPException(status_code=400, detail="Invalid role ID")
    if payload.customRoleId:
        role_exists = await custom_roles_col.find_one({"_id": ObjectId(payload.customRoleId)})
        if not role_exists:
            raise HTTPException(status_code=404, detail="Role not found")

    result = await users_col.find_one_and_update(
        {"_id": ObjectId(user_id), "role": "staff"},
        {"$set": {"customRoleId": payload.customRoleId}},
        return_document=True,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Staff user not found")

    await log_action(
        actor_id=str(user["_id"]), actor_email=user.get("email", ""),
        action="staff_custom_role_assigned", target_type="user", target_id=user_id,
        details={"customRoleId": payload.customRoleId},
    )

    return {"userId": user_id, "customRoleId": payload.customRoleId}
