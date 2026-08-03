"""
Vendor endpoints.

GET  /api/vendors?category=            -> list vendors, sortable by the client
POST /api/vendors                      -> create a vendor record (staff)
PATCH /api/maintenance/tickets/:id/assign-vendor -> assign a vendor to a ticket

See the NOTE in models.py: distance/arrival numbers here are manually
maintained on the vendor record, not computed from real addresses.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends
from bson import ObjectId

from db import vendors_col, tickets_col
from models import VendorCreate, VendorAssign
from auth import require_staff
import notifications_service

router = APIRouter(prefix="/api/vendors", tags=["vendors"])


def serialize(v: dict) -> dict:
    v["id"] = str(v.pop("_id"))
    return v


@router.get("")
async def list_vendors(category: str | None = None, user: dict = Depends(require_staff)):
    query = {"active": True}
    if category:
        query["category"] = category
    cursor = vendors_col.find(query).sort("rating", -1)
    vendors = await cursor.to_list(length=200)
    return {"vendors": [serialize(v) for v in vendors]}


@router.post("")
async def create_vendor(payload: VendorCreate, user: dict = Depends(require_staff)):
    doc = payload.model_dump()
    doc["createdAt"] = datetime.now(timezone.utc)
    result = await vendors_col.insert_one(doc)
    doc["_id"] = result.inserted_id
    return serialize(doc)


# Mounted under /api/maintenance/tickets to keep the ticket update in one
# logical place, even though the vendor data itself lives in this router.
ticket_assign_router = APIRouter(prefix="/api/maintenance/tickets", tags=["maintenance", "vendors"])


@ticket_assign_router.patch("/{ticket_id}/assign-vendor")
async def assign_vendor_to_ticket(ticket_id: str, payload: VendorAssign, user: dict = Depends(require_staff)):
    if not ObjectId.is_valid(ticket_id) or not ObjectId.is_valid(payload.vendorId):
        raise HTTPException(status_code=400, detail="Invalid ticket or vendor ID")

    vendor = await vendors_col.find_one({"_id": ObjectId(payload.vendorId)})
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")

    updates = {
        "assignedVendorId": payload.vendorId,
        "assignedVendorName": vendor["name"],
        "estimatedCost": payload.estimatedCost if payload.estimatedCost is not None else vendor.get("baseCost"),
        "estimatedArrivalHours": payload.estimatedArrivalHours if payload.estimatedArrivalHours is not None else vendor.get("avgArrivalHours"),
        "status": "in_progress",
        "updatedAt": datetime.now(timezone.utc),
    }
    result = await tickets_col.find_one_and_update(
        {"_id": ObjectId(ticket_id)}, {"$set": updates}, return_document=True
    )
    if not result:
        raise HTTPException(status_code=404, detail="Ticket not found")

    eta = updates.get("estimatedArrivalHours")
    await notifications_service.notify_unit_resident(
        result.get("propertyId"), result.get("unitId"),
        type="vendor_assigned",
        title=f"{vendor['name']} assigned to your request",
        body=f"{result.get('title', 'Your maintenance request')}" + (f" — ETA ~{eta}h" if eta else ""),
        link=f"/maintenance/{ticket_id}",
    )

    result["id"] = str(result.pop("_id"))
    return result
