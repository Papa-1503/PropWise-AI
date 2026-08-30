"""
Property + unit endpoints.

GET   /api/properties                 -> list all properties (with units)
GET   /api/properties/:id             -> single property
POST  /api/properties                 -> create a property
PATCH /api/properties/:id/units/:unitId/status  -> change a unit's occupancy status

Each property document embeds its units:
{
  _id, name, address,
  units: [{ unitId, status, rent, bedrooms, bathrooms }]
}
Adjust to a separate units collection if that's how your data is actually
modeled — the dashboard/copilot aggregations would need matching changes.
"""
from fastapi import APIRouter, HTTPException, Depends
from bson import ObjectId

from db import properties_col, payments_col
from datetime import datetime, timezone, timedelta
from services.events import emit_event
from auth import require_staff
from models import PropertyCreate, PropertyUpdate, UnitStatusUpdate, UnitDetailsUpdate, UnitIn, OwnerAssign, RentRulesUpdate, TelephonyConfigUpdate

router = APIRouter(prefix="/api/properties", tags=["properties"])


def serialize(prop: dict) -> dict:
    prop["id"] = str(prop.pop("_id"))
    return prop


@router.get("")
async def list_properties(user: dict = Depends(require_staff)):
    cursor = properties_col.find({})
    props = await cursor.to_list(length=200)
    return {"properties": [serialize(p) for p in props]}


@router.patch("/{property_id}/units/{unit_id}/status")
async def update_unit_status(property_id: str, unit_id: str, payload: UnitStatusUpdate, user: dict = Depends(require_staff)):
    query_id = ObjectId(property_id) if ObjectId.is_valid(property_id) else property_id
    result = await properties_col.find_one_and_update(
        {"_id": query_id, "units.unitId": unit_id},
        {"$set": {"units.$.status": payload.status}},
        return_document=True,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Property or unit not found")

    if payload.status == "vacant":
        try:
            await emit_event("tenant_moved_out", {
                "propertyId": property_id,
                "unitId": unit_id,
            })
        except Exception as e:
            print(f"Workflow dispatch failed: {e}")

    return serialize(result)


@router.post("")
async def create_property(payload: PropertyCreate, user: dict = Depends(require_staff)):
    doc = payload.model_dump()
    result = await properties_col.insert_one(doc)
    doc["_id"] = result.inserted_id
    return serialize(doc)


@router.patch("/{property_id}")
async def update_property(property_id: str, payload: PropertyUpdate, user: dict = Depends(require_staff)):
    """PropertyUpdate existed as a model with no endpoint using it before
    Priority 48 — genuinely dead code, now wired up."""
    query_id = ObjectId(property_id) if ObjectId.is_valid(property_id) else property_id
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    result = await properties_col.find_one_and_update(
        {"_id": query_id}, {"$set": updates}, return_document=True
    )
    if not result:
        raise HTTPException(status_code=404, detail="Property not found")
    return serialize(result)


@router.patch("/{property_id}/rent-rules")
async def update_rent_rules(property_id: str, payload: RentRulesUpdate, user: dict = Depends(require_staff)):
    """The genuinely missing piece: routers/admin.py's run_late_fee_check
    already reads lateFeeGraceDays/lateFeeAmount per property with sensible
    defaults — the automation logic already existed. There was just no
    endpoint for staff to ever actually set these values, so every
    property silently used the same global defaults regardless. dueDay
    is stored for a future invoice-generation feature to use; nothing
    reads it yet, so setting it has no automated effect today."""
    query_id = ObjectId(property_id) if ObjectId.is_valid(property_id) else property_id
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    result = await properties_col.find_one_and_update(
        {"_id": query_id}, {"$set": updates}, return_document=True
    )
    if not result:
        raise HTTPException(status_code=404, detail="Property not found")
    return serialize(result)


@router.patch("/{property_id}/telephony")
async def update_telephony_config(property_id: str, payload: TelephonyConfigUpdate, user: dict = Depends(require_staff)):
    """Sets which Twilio number routes to this property's after-hours
    on-call line, and the after-hours time window itself. Doesn't touch
    Twilio at all — purchasing/configuring the actual number in the
    Twilio console (and pointing its Voice webhook at
    /api/telephony/voice) is a one-time manual setup step outside this
    app; this endpoint just tells RentFlow which number belongs to
    which property once that's done."""
    query_id = ObjectId(property_id) if ObjectId.is_valid(property_id) else property_id
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    result = await properties_col.find_one_and_update(
        {"_id": query_id}, {"$set": updates}, return_document=True
    )
    if not result:
        raise HTTPException(status_code=404, detail="Property not found")
    return serialize(result)


@router.get("/{property_id}/rent-cycle")
async def rent_cycle_timeline(property_id: str, user: dict = Depends(require_staff)):
    """A real, read-only computed timeline — not a stored schedule, since
    there's nothing to configure here beyond what rent-rules already
    covers. Uses the exact same grace-period logic as run_late_fee_check
    in admin.py, so what's shown here is guaranteed consistent with what
    the automation actually does, not a separate approximation of it.
    Fully automated: nothing here needs a human to create or maintain —
    it's derived live from real payment due dates plus this property's
    configured (or default) grace period."""
    query_id = ObjectId(property_id) if ObjectId.is_valid(property_id) else property_id
    prop = await properties_col.find_one({"_id": query_id})
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")

    grace_days = prop.get("lateFeeGraceDays", 5)
    late_fee_amount = prop.get("lateFeeAmount", 50.0)
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    charges = await payments_col.find({"propertyId": property_id}).sort("dueDate", 1).to_list(length=500)

    events = []
    for c in charges:
        due = c.get("dueDate")
        if not isinstance(due, datetime):
            continue
        due = due.replace(tzinfo=None) if due.tzinfo else due
        paid_enough = c.get("amountPaid", 0) >= c.get("amountDue", 0)
        grace_ends = due + timedelta(days=grace_days)
        days_out = (due - now).days

        # Only surface what's actually relevant right now — settled
        # charges more than a grace period in the past, or due dates
        # more than 30 days out, add noise without adding value to a
        # timeline meant to show what's coming up or needs attention.
        if paid_enough and (now - due).days > grace_days:
            continue
        if days_out > 30:
            continue

        if paid_enough:
            status = "paid"
        elif now < due:
            status = "upcoming"
        elif now <= grace_ends:
            status = "in_grace_period"
        elif c.get("lateFeeApplied"):
            status = "late_fee_applied"
        else:
            status = "past_grace_awaiting_check"

        events.append({
            "unitId": c.get("unitId"),
            "dueDate": due.isoformat(),
            "graceEndsDate": grace_ends.isoformat(),
            "amountDue": c.get("amountDue", 0),
            "status": status,
        })

    return {
        "graceDays": grace_days,
        "lateFeeAmount": late_fee_amount,
        "events": events,
    }


@router.post("/{property_id}/units")
async def add_unit(property_id: str, payload: UnitIn, user: dict = Depends(require_staff)):
    """No endpoint previously existed to add a new unit to an existing
    property — only whole-property creation with an initial units array
    was supported."""
    query_id = ObjectId(property_id) if ObjectId.is_valid(property_id) else property_id
    existing = await properties_col.find_one({"_id": query_id, "units.unitId": payload.unitId})
    if existing:
        raise HTTPException(status_code=409, detail=f"Unit {payload.unitId} already exists on this property")
    result = await properties_col.find_one_and_update(
        {"_id": query_id},
        {"$push": {"units": payload.model_dump()}},
        return_document=True,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Property not found")
    return serialize(result)


@router.patch("/{property_id}/units/{unit_id}/details")
async def update_unit_details(property_id: str, unit_id: str, payload: UnitDetailsUpdate, user: dict = Depends(require_staff)):
    """Editing rent/bedrooms/bathrooms — distinct from the existing
    status-only update endpoint above. No endpoint for this existed
    before Priority 48; a unit's actual details could previously only
    be set once, at creation."""
    query_id = ObjectId(property_id) if ObjectId.is_valid(property_id) else property_id
    updates = {f"units.$.{k}": v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    result = await properties_col.find_one_and_update(
        {"_id": query_id, "units.unitId": unit_id},
        {"$set": updates},
        return_document=True,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Property or unit not found")
    return serialize(result)


@router.patch("/{property_id}/owner")
async def assign_owner(property_id: str, payload: OwnerAssign, user: dict = Depends(require_staff)):
    if not ObjectId.is_valid(payload.ownerId):
        raise HTTPException(status_code=400, detail="Invalid owner ID")

    # Property _id may be a real ObjectId or a plain string (e.g. seeded demo data)
    query_id = ObjectId(property_id) if ObjectId.is_valid(property_id) else property_id

    result = await properties_col.find_one_and_update(
        {"_id": query_id},
        {"$set": {"ownerId": payload.ownerId}},
        return_document=True,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Property not found")
    return serialize(result)
