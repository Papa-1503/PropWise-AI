"""
Upfront damage cost estimates (P14) — parts + labor, no retailer API
needed.

Deliberately simple, per the reconciled roadmap's own revised scope:
construct a Home Depot / Amazon SEARCH link at request time (URL
encoding only, no API keys, no partner access, no scraping) rather
than fetch a live price. No ongoing API cost, no rate limits, nothing
to break if a retailer changes their backend - the tenant clicks
through and sees the real, current price themselves on the retailer's
own site. The tradeoff, stated honestly: this makes the link a
transparency/verification tool, not the pricing source of truth - the
estimate itself still depends on the staff-entered labor hours and
labor rate below.

GET  /api/repair-items                 -> list the reference catalog
POST /api/repair-items                 -> add a damage-type -> part/labor mapping
GET  /api/labor-rates                  -> list $/hour by category
POST /api/labor-rates                  -> set a category's rate
GET  /api/repair-items/{id}/estimate   -> the real computed estimate for one
                                           catalog entry (labor cost + retailer
                                           links), used both standalone and by
                                           the flagged-item estimate below
GET  /api/inspections/{id}/items/{item_id}/estimate
                                        -> the real per-flagged-item estimate,
                                           matched to a repair_items entry by
                                           damageType == the item's description
"""
from urllib.parse import quote_plus

from fastapi import APIRouter, HTTPException, Depends
from bson import ObjectId

from db import repair_items_col, labor_rates_col, inspections_col
from models import RepairItemCreate, LaborRateCreate
from auth import require_staff

router = APIRouter(tags=["repair-estimates"])


def build_retailer_links(search_query: str) -> dict:
    encoded = quote_plus(search_query)
    return {
        "homeDepot": f"https://www.homedepot.com/s/{encoded}",
        "amazon": f"https://www.amazon.com/s?k={encoded}",
    }


async def compute_estimate(repair_item: dict) -> dict:
    rate_doc = await labor_rates_col.find_one({"category": repair_item["category"]})
    hourly_rate = rate_doc["hourlyRate"] if rate_doc else 0
    labor_cost = round(repair_item["laborHours"] * hourly_rate, 2)
    return {
        "partName": repair_item["partName"],
        "laborHours": repair_item["laborHours"],
        "hourlyRate": hourly_rate,
        "laborCost": labor_cost,
        "hasRateOnFile": rate_doc is not None,
        "retailerLinks": build_retailer_links(repair_item["searchQuery"]),
    }


def serialize(doc: dict) -> dict:
    doc = dict(doc)
    doc["id"] = str(doc.pop("_id"))
    return doc


@router.post("/api/repair-items")
async def create_repair_item(payload: RepairItemCreate, user: dict = Depends(require_staff)):
    doc = payload.model_dump()
    result = await repair_items_col.insert_one(doc)
    doc["_id"] = result.inserted_id
    return serialize(doc)


@router.get("/api/repair-items")
async def list_repair_items(user: dict = Depends(require_staff)):
    items = await repair_items_col.find({}).sort("damageType", 1).to_list(length=500)
    return {"repairItems": [serialize(i) for i in items]}


@router.get("/api/repair-items/{repair_item_id}/estimate")
async def get_repair_item_estimate(repair_item_id: str, user: dict = Depends(require_staff)):
    if not ObjectId.is_valid(repair_item_id):
        raise HTTPException(status_code=400, detail="Invalid repair item ID")
    repair_item = await repair_items_col.find_one({"_id": ObjectId(repair_item_id)})
    if not repair_item:
        raise HTTPException(status_code=404, detail="Repair item not found")
    return await compute_estimate(repair_item)


@router.post("/api/labor-rates")
async def set_labor_rate(payload: LaborRateCreate, user: dict = Depends(require_staff)):
    """Upsert by category - a business updating its own $/hour figure
    should replace the existing rate for that category, not create a
    second, ambiguous one."""
    await labor_rates_col.update_one(
        {"category": payload.category},
        {"$set": {"hourlyRate": payload.hourlyRate}},
        upsert=True,
    )
    return {"category": payload.category, "hourlyRate": payload.hourlyRate}


@router.get("/api/labor-rates")
async def list_labor_rates(user: dict = Depends(require_staff)):
    rates = await labor_rates_col.find({}).sort("category", 1).to_list(length=100)
    return {"laborRates": [{"category": r["category"], "hourlyRate": r["hourlyRate"]} for r in rates]}


@router.get("/api/inspections/{inspection_id}/items/{item_id}/estimate")
async def get_flagged_item_estimate(inspection_id: str, item_id: str, user: dict = Depends(require_staff)):
    """Links a real flagged/failed inspection item to the repair_items
    catalog by matching the item's description against a catalog
    entry's damageType (case-insensitive substring match, consistent
    with the regex-search approach already established elsewhere in
    this app rather than introducing a different matching mechanism
    for one feature). No match found is an honest, expected outcome
    for damage types the catalog hasn't been populated for yet - not
    an error, just no estimate available yet."""
    if not ObjectId.is_valid(inspection_id):
        raise HTTPException(status_code=400, detail="Invalid inspection ID")
    inspection = await inspections_col.find_one({"_id": ObjectId(inspection_id)})
    if not inspection:
        raise HTTPException(status_code=404, detail="Inspection not found")

    item = next((i for i in inspection.get("items", []) if i.get("id") == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found on this inspection")
    if item.get("status") not in ("flag", "fail"):
        raise HTTPException(status_code=400, detail="Only flagged or failed items have a damage estimate.")

    description = item.get("description", "")
    if not description:
        return {"matched": False, "reason": "This item has no description to match against the repair catalog."}

    repair_item = await repair_items_col.find_one({"damageType": {"$regex": description, "$options": "i"}})
    if not repair_item:
        return {"matched": False, "reason": "No matching repair catalog entry found for this damage type yet."}

    estimate = await compute_estimate(repair_item)
    return {"matched": True, "damageType": repair_item["damageType"], **estimate}
