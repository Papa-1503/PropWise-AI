"""
Smart lock control — real, live functionality once SEAM_API_KEY is
configured and a unit's seamDeviceId is set (see models.py's UnitIn).
Until then, every endpoint here returns an honest 501, not a silent
no-op or a fabricated success.

GET    /api/smart-locks/devices                                    -> list connected Seam devices
POST   /api/smart-locks/{property_id}/units/{unit_id}/lock          -> lock the unit's door
POST   /api/smart-locks/{property_id}/units/{unit_id}/unlock        -> unlock the unit's door
POST   /api/smart-locks/{property_id}/units/{unit_id}/access-code   -> issue a real, time-bounded PIN
GET    /api/smart-locks/{property_id}/units/{unit_id}/access-log    -> real audit trail of codes issued
DELETE /api/smart-locks/access-codes/{access_code_id}                -> revoke a code early
"""
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends
from bson import ObjectId

from db import properties_col, smart_lock_access_log_col
from models import AccessCodeCreate
from auth import require_staff
from audit_service import log_action
import seam_service
from seam_service import SeamNotConfigured, SeamApiError

router = APIRouter(prefix="/api/smart-locks", tags=["smart-locks"])


async def _find_unit_device_id(property_id: str, unit_id: str) -> str:
    """Looks up the real Seam device_id linked to a unit, or raises a
    clear, honest error — never silently proceeds with no device."""
    query_id = ObjectId(property_id) if ObjectId.is_valid(property_id) else property_id
    property_doc = await properties_col.find_one({"_id": query_id})
    if not property_doc:
        raise HTTPException(status_code=404, detail="Property not found")
    unit = next((u for u in property_doc.get("units", []) if u.get("unitId") == unit_id), None)
    if not unit:
        raise HTTPException(status_code=404, detail="Unit not found on this property")
    device_id = unit.get("seamDeviceId")
    if not device_id:
        raise HTTPException(
            status_code=400,
            detail="This unit has no smart lock linked yet — set seamDeviceId via PATCH /api/properties/{id}/units/{unitId}/details.",
        )
    return device_id


@router.get("/devices")
async def list_devices(user: dict = Depends(require_staff)):
    try:
        devices = await seam_service.list_devices_async()
    except SeamNotConfigured as exc:
        raise HTTPException(status_code=501, detail=str(exc))
    except SeamApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"devices": devices}


@router.post("/{property_id}/units/{unit_id}/lock")
async def lock_unit(property_id: str, unit_id: str, user: dict = Depends(require_staff)):
    device_id = await _find_unit_device_id(property_id, unit_id)
    try:
        result = await seam_service.lock_door_async(device_id)
    except SeamNotConfigured as exc:
        raise HTTPException(status_code=501, detail=str(exc))
    except SeamApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    await log_action(
        actor_id=str(user["id"]), actor_email=user.get("email", ""),
        action="smart_lock_locked", target_type="unit", target_id=f"{property_id}/{unit_id}",
        details={},
    )
    return result


@router.post("/{property_id}/units/{unit_id}/unlock")
async def unlock_unit(property_id: str, unit_id: str, user: dict = Depends(require_staff)):
    device_id = await _find_unit_device_id(property_id, unit_id)
    try:
        result = await seam_service.unlock_door_async(device_id)
    except SeamNotConfigured as exc:
        raise HTTPException(status_code=501, detail=str(exc))
    except SeamApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    await log_action(
        actor_id=str(user["id"]), actor_email=user.get("email", ""),
        action="smart_lock_unlocked", target_type="unit", target_id=f"{property_id}/{unit_id}",
        details={},
    )
    return result


@router.post("/{property_id}/units/{unit_id}/access-code")
async def issue_access_code(property_id: str, unit_id: str, payload: AccessCodeCreate, user: dict = Depends(require_staff)):
    """Issues a real, time-bounded PIN code on the unit's physical lock
    and logs it — the genuine audit trail of who was given access, for
    what unit, by whom, and when it expires. Never overwrites the log
    on failure: a rejected Seam call raises before anything is
    recorded, so the log only ever reflects codes that actually made
    it onto a real lock."""
    device_id = await _find_unit_device_id(property_id, unit_id)
    try:
        result = await seam_service.create_access_code_async(
            device_id, payload.name, payload.code, payload.startsAt, payload.endsAt,
        )
    except SeamNotConfigured as exc:
        raise HTTPException(status_code=501, detail=str(exc))
    except SeamApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    access_code = result.get("access_code", {})
    log_doc = {
        "propertyId": property_id, "unitId": unit_id,
        "deviceId": device_id,
        "seamAccessCodeId": access_code.get("access_code_id"),
        "name": payload.name,
        "startsAt": payload.startsAt, "endsAt": payload.endsAt,
        "issuedBy": user.get("email"),
        "revoked": False,
        "createdAt": datetime.now(timezone.utc),
    }
    await smart_lock_access_log_col.insert_one(log_doc)

    await log_action(
        actor_id=str(user["id"]), actor_email=user.get("email", ""),
        action="smart_lock_access_code_issued", target_type="unit", target_id=f"{property_id}/{unit_id}",
        details={"name": payload.name, "endsAt": payload.endsAt},
    )

    return result


@router.get("/{property_id}/units/{unit_id}/access-log")
async def get_access_log(property_id: str, unit_id: str, user: dict = Depends(require_staff)):
    cursor = smart_lock_access_log_col.find(
        {"propertyId": property_id, "unitId": unit_id}
    ).sort("createdAt", -1).limit(100)
    entries = await cursor.to_list(length=100)
    for e in entries:
        e["id"] = str(e.pop("_id"))
        if isinstance(e.get("createdAt"), datetime):
            e["createdAt"] = e["createdAt"].isoformat()
    return {"entries": entries}


@router.delete("/access-codes/{access_code_id}")
async def revoke_access_code(access_code_id: str, user: dict = Depends(require_staff)):
    """access_code_id here is Seam's own ID (seamAccessCodeId in the log
    above), not this app's log entry ID — matches what /access-code
    returned, so staff can revoke directly from that response without
    a separate lookup."""
    try:
        await seam_service.delete_access_code_async(access_code_id)
    except SeamNotConfigured as exc:
        raise HTTPException(status_code=501, detail=str(exc))
    except SeamApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    await smart_lock_access_log_col.update_one(
        {"seamAccessCodeId": access_code_id},
        {"$set": {"revoked": True, "revokedAt": datetime.now(timezone.utc), "revokedBy": user.get("email")}},
    )

    await log_action(
        actor_id=str(user["id"]), actor_email=user.get("email", ""),
        action="smart_lock_access_code_revoked", target_type="access_code", target_id=access_code_id,
        details={},
    )
    return {"revoked": True}
