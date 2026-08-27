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


def _normalize_lower_better(value, values):
    """1.0 = best (lowest) in the set, 0.0 = worst (highest). None values
    get a neutral 0.5 rather than being penalized or excluded — a vendor
    that simply hasn't had a field filled in shouldn't rank artificially
    low against ones that have."""
    present = [v for v in values if v is not None]
    if value is None or len(present) < 2:
        return 0.5
    lo, hi = min(present), max(present)
    if hi == lo:
        return 0.5
    return 1 - ((value - lo) / (hi - lo))


@router.get("/recommended")
async def recommended_vendors(category: str, user: dict = Depends(require_staff)):
    """Ranks active vendors in a category by a single transparent composite
    score, rather than staff having to pick one factor (rating, cost,
    distance, arrival) at a time and manually weigh trade-offs themselves.

    Same philosophy as the dashboard health score and the applicant
    screening score elsewhere in this app: a simple, explainable weighted
    formula, not a statistical model — the weights are a starting point,
    not a claim of optimality. All four factors are normalized relative
    to the other candidates in this specific category (not an absolute
    scale), since "cheap" or "close" means different things for a
    locksmith than for an HVAC contractor.
    """
    cursor = vendors_col.find({"active": True, "category": category})
    vendors = await cursor.to_list(length=200)
    if not vendors:
        return {"vendors": []}

    ratings = [v.get("rating") for v in vendors]
    arrivals = [v.get("avgArrivalHours") for v in vendors]
    costs = [v.get("baseCost") for v in vendors]
    distances = [v.get("distanceMiles") for v in vendors]

    scored = []
    for v in vendors:
        rating_component = ((v.get("rating") or 0) / 5) * 40
        speed_component = _normalize_lower_better(v.get("avgArrivalHours"), arrivals) * 25
        cost_component = _normalize_lower_better(v.get("baseCost"), costs) * 20
        distance_component = _normalize_lower_better(v.get("distanceMiles"), distances) * 15
        score = round(rating_component + speed_component + cost_component + distance_component, 1)

        reason_parts = [f"{v.get('rating', '?')}★ rating"]
        if v.get("baseCost") is not None:
            cheapest = min((c for c in costs if c is not None), default=None)
            reason_parts.append(f"${v['baseCost']:.0f}" + (" (cheapest)" if v["baseCost"] == cheapest else ""))
        if v.get("distanceMiles") is not None:
            closest = min((d for d in distances if d is not None), default=None)
            reason_parts.append(f"{v['distanceMiles']}mi" + (" (closest)" if v["distanceMiles"] == closest else ""))
        if v.get("avgArrivalHours") is not None:
            fastest = min((a for a in arrivals if a is not None), default=None)
            reason_parts.append(f"~{v['avgArrivalHours']}h arrival" + (" (fastest)" if v["avgArrivalHours"] == fastest else ""))

        vs = serialize({**v})
        vs["score"] = score
        vs["reason"] = ", ".join(reason_parts)
        scored.append(vs)

    scored.sort(key=lambda v: v["score"], reverse=True)
    return {"vendors": scored}


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
