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

from db import properties_col
from services.events import emit_event
from auth import require_staff
from models import PropertyCreate, PropertyUpdate, UnitStatusUpdate,  OwnerAssign

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
    if not ObjectId.is_valid(property_id):
        raise HTTPException(status_code=400, detail="Invalid property ID")
    result = await properties_col.find_one_and_update(
        {"_id": ObjectId(property_id), "units.unitId": unit_id},
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


@router.patch("/{property_id}/units/{unit_id}/status")
async def update_unit_status(property_id: str, unit_id: str, payload: UnitStatusUpdate, user: dict = Depends(require_staff)):
    if not ObjectId.is_valid(property_id):
        raise HTTPException(status_code=400, detail="Invalid property ID")
    result = await properties_col.find_one_and_update(
        {"_id": ObjectId(property_id), "units.unitId": unit_id},
        {"$set": {"units.$.status": payload.status}},
        return_document=True,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Property or unit not found")
    return serialize(result)
@router.patch("/{property_id}/owner")
async def assign_owner(property_id: str, payload: OwnerAssign, user: dict = Depends(require_staff)):
    if not ObjectId.is_valid(property_id):
        raise HTTPException(status_code=400, detail="Invalid property ID")
    if not ObjectId.is_valid(payload.ownerId):
        raise HTTPException(status_code=400, detail="Invalid owner ID")
    result = await properties_col.find_one_and_update(
        {"_id": ObjectId(property_id)},
        {"$set": {"ownerId": payload.ownerId}},
        return_document=True,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Property not found")
    return serialize(result)
