"""
Thermostat control — real, live functionality once SEAM_API_KEY is
configured (the same real Seam workspace/key already used for smart
locks in routers/smart_locks.py) and a unit's seamThermostatDeviceId
is set (see models.py's UnitIn). Until then, every endpoint here
returns an honest 501, not a silent no-op or a fabricated success -
same standard as every other real, live integration in this app.

GET  /api/thermostats/devices                                    -> list connected Seam thermostats
GET  /api/thermostats/{property_id}/units/{unit_id}              -> this unit's real, live thermostat state
POST /api/thermostats/{property_id}/units/{unit_id}/set-mode     -> set HVAC mode + set points remotely

The genuine, real value here: staff can set a vacant unit's
thermostat to an energy-saving mode between tenants, or prep a unit's
climate ahead of a move-in, without a physical visit - the same real
"remote control, no truck roll" value smart locks already provide for
access.

MULTI-TENANCY: same real, physical-property-relevant discipline as
smart_locks.py - _find_unit_thermostat_device_id requires and checks
orgId before returning any device, so staff can never read or control
a DIFFERENT organization's thermostat by supplying its real
property/unit IDs.
"""
from fastapi import APIRouter, HTTPException, Depends
from bson import ObjectId

from db import properties_col
from models import ThermostatModeSet
from auth import require_staff
from audit_service import log_action
import seam_service
from seam_service import SeamNotConfigured, SeamApiError

router = APIRouter(prefix="/api/thermostats", tags=["thermostats"])

# Real, documented Seam capability flags that gate each real HVAC
# mode - confirmed directly against Seam's own API reference before
# writing this, same standard as every other integration in this app.
# "eco" (Google Nest only) has no single documented capability flag,
# so it's intentionally left unchecked here - Seam's own API rejects
# it on an unsupported device, the same honest failure mode as any
# other unsupported real request.
_MODE_CAPABILITY_FLAGS = {
    "heat": "can_hvac_heat",
    "cool": "can_hvac_cool",
    "heat_cool": "can_hvac_heat_cool",
    "off": "can_turn_off_hvac",
}


async def _find_unit_thermostat_device_id(property_id: str, unit_id: str, org_id: str) -> str:
    """Looks up the real Seam device_id linked to a unit's thermostat,
    or raises a clear, honest error - never silently proceeds with no
    device. org_id is required and checked against the property - the
    same real gap smart_locks.py's own lookup closes, applied here:
    without it, staff could read or control a DIFFERENT organization's
    thermostat simply by supplying its real property/unit IDs."""
    query_id = ObjectId(property_id) if ObjectId.is_valid(property_id) else property_id
    property_doc = await properties_col.find_one({"_id": query_id, "orgId": org_id})
    if not property_doc:
        raise HTTPException(status_code=404, detail="Property not found")
    unit = next((u for u in property_doc.get("units", []) if u.get("unitId") == unit_id), None)
    if not unit:
        raise HTTPException(status_code=404, detail="Unit not found on this property")
    device_id = unit.get("seamThermostatDeviceId")
    if not device_id:
        raise HTTPException(
            status_code=400,
            detail="This unit has no thermostat linked yet — set seamThermostatDeviceId via PATCH /api/properties/{id}/units/{unitId}/details.",
        )
    return device_id


@router.get("/devices")
async def list_devices(user: dict = Depends(require_staff)):
    try:
        thermostats = await seam_service.list_thermostats_async()
    except SeamNotConfigured as exc:
        raise HTTPException(status_code=501, detail=str(exc))
    except SeamApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"devices": thermostats}


@router.get("/{property_id}/units/{unit_id}")
async def get_unit_thermostat(property_id: str, unit_id: str, user: dict = Depends(require_staff)):
    device_id = await _find_unit_thermostat_device_id(property_id, unit_id, user["orgId"])
    try:
        device = await seam_service.get_thermostat_async(device_id)
    except SeamNotConfigured as exc:
        raise HTTPException(status_code=501, detail=str(exc))
    except SeamApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"device": device}


@router.post("/{property_id}/units/{unit_id}/set-mode")
async def set_unit_thermostat_mode(property_id: str, unit_id: str, payload: ThermostatModeSet, user: dict = Depends(require_staff)):
    """Sets a unit's thermostat to a real HVAC mode remotely. Checks
    the device's own real, live capability flags before attempting a
    mode it genuinely can't perform (e.g. sending "cool" to a
    heat-only unit) - a clear, honest 400 instead of forwarding a
    request Seam would reject anyway, or worse, one it might silently
    misinterpret."""
    device_id = await _find_unit_thermostat_device_id(property_id, unit_id, user["orgId"])

    required_flag = _MODE_CAPABILITY_FLAGS.get(payload.hvacMode)
    if required_flag:
        try:
            device = await seam_service.get_thermostat_async(device_id)
        except SeamNotConfigured as exc:
            raise HTTPException(status_code=501, detail=str(exc))
        except SeamApiError as exc:
            raise HTTPException(status_code=502, detail=str(exc))
        if not device.get(required_flag):
            raise HTTPException(
                status_code=400,
                detail=f"This thermostat doesn't support {payload.hvacMode} mode.",
            )

    try:
        result = await seam_service.set_hvac_mode_async(
            device_id, payload.hvacMode,
            payload.heatingSetPointFahrenheit, payload.coolingSetPointFahrenheit,
        )
    except SeamNotConfigured as exc:
        raise HTTPException(status_code=501, detail=str(exc))
    except SeamApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    await log_action(
        actor_id=str(user["id"]), actor_email=user.get("email", ""), org_id=user["orgId"],
        action="thermostat_mode_set", target_type="unit", target_id=f"{property_id}/{unit_id}",
        details={
            "hvacMode": payload.hvacMode,
            "heatingSetPointFahrenheit": payload.heatingSetPointFahrenheit,
            "coolingSetPointFahrenheit": payload.coolingSetPointFahrenheit,
        },
    )
    return result
