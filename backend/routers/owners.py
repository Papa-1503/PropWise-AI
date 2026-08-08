"""
Owner portal endpoints — read-only views scoped to properties an owner
actually owns. Every query filters on ownerId == current user's id,
not just role-gated, so one owner can never see another owner's data.
"""
from fastapi import APIRouter, Depends
from bson import ObjectId

from db import properties_col, payments_col, tickets_col
from auth import require_owner

router = APIRouter(prefix="/api/owners", tags=["owners"])


def serialize(doc: dict) -> dict:
    doc["id"] = str(doc.pop("_id"))
    return doc


async def _owned_property_ids(user_id: str) -> list[str]:
    cursor = properties_col.find({"ownerId": user_id}, {"_id": 1})
    props = await cursor.to_list(length=500)
    return [str(p["_id"]) for p in props]


@router.get("/me/properties")
async def list_my_properties(user: dict = Depends(require_owner)):
    cursor = properties_col.find({"ownerId": user["id"]})
    props = await cursor.to_list(length=500)
    return {"properties": [serialize(p) for p in props]}


@router.get("/me/dashboard")
async def owner_dashboard(user: dict = Depends(require_owner)):
    props = await properties_col.find({"ownerId": user["id"]}).to_list(length=500)
    property_ids = [str(p["_id"]) for p in props]

    unit_count = 0
    occupied = 0
    for p in props:
        units = p.get("units", [])
        unit_count += len(units)
        occupied += sum(1 for u in units if u.get("status") == "occupied")

    open_maintenance = 0
    if property_ids:
        open_maintenance = await tickets_col.count_documents({
            "propertyId": {"$in": property_ids},
            "status": {"$in": ["open", "in_progress"]},
        })

    return {
        "propertyCount": len(props),
        "unitCount": unit_count,
        "occupiedUnits": occupied,
        "vacantUnits": unit_count - occupied,
        "occupancyRate": round((occupied / unit_count) * 100, 1) if unit_count else 0,
        "openMaintenanceCount": open_maintenance,
    }


@router.get("/me/statements")
async def owner_statements(user: dict = Depends(require_owner)):
    props = await properties_col.find({"ownerId": user["id"]}).to_list(length=500)

    statements = []
    grand_billed = 0.0
    grand_collected = 0.0

    for p in props:
        property_id = str(p["_id"])
        charges = await payments_col.find({"propertyId": property_id}).to_list(length=1000)

        billed = sum(c.get("amountDue", 0) for c in charges)
        collected = sum(c.get("amountPaid", 0) for c in charges)
        outstanding = billed - collected

        statements.append({
            "propertyId": property_id,
            "propertyName": p.get("name", ""),
            "totalBilled": round(billed, 2),
            "totalCollected": round(collected, 2),
            "outstanding": round(outstanding, 2),
            "chargeCount": len(charges),
        })

        grand_billed += billed
        grand_collected += collected

    return {
        "properties": statements,
        "totals": {
            "totalBilled": round(grand_billed, 2),
            "totalCollected": round(grand_collected, 2),
            "outstanding": round(grand_billed - grand_collected, 2),
        },
    }
