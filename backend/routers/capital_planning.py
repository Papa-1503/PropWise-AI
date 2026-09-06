"""
Capital projects & fixed-asset planning (P27).

GET/POST   /api/fixed-assets                  -> asset CRUD
PATCH      /api/fixed-assets/{id}
GET        /api/fixed-assets/end-of-life       -> the real proactive-planning
                                                   view - assets approaching
                                                   or past their expected
                                                   replacement date
GET/POST   /api/capital-projects               -> project CRUD
PATCH      /api/capital-projects/{id}

Distinct from Priority 21's Budgeting module (already built this
session): a fixed asset's expected end-of-life is a genuinely
different concept from a monthly expense budget, though a planned
capital project can name which budget period it's meant to line up
with (CapitalProjectCreate.budgetPeriod) - real cross-referencing, not
automatic linkage, since deciding whether a specific project actually
belongs in a specific month's budget is a staff judgment call, not
something this endpoint should silently assume.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends
from bson import ObjectId

from db import fixed_assets_col, capital_projects_col
from models import FixedAssetCreate, FixedAssetUpdate, CapitalProjectCreate, CapitalProjectUpdate
from date_utils import parse_date_utc
from auth import require_staff

router = APIRouter(tags=["capital-planning"])


def serialize(doc: dict) -> dict:
    doc = dict(doc)
    doc["id"] = str(doc.pop("_id"))
    for field in ("installDate", "targetDate", "createdAt"):
        if isinstance(doc.get(field), datetime):
            doc[field] = doc[field].isoformat()
    return doc


# ---------- Fixed assets ----------

@router.post("/api/fixed-assets")
async def create_fixed_asset(payload: FixedAssetCreate, user: dict = Depends(require_staff)):
    doc = payload.model_dump()
    doc["orgId"] = user["orgId"]
    doc["installDate"] = parse_date_utc(doc["installDate"])
    doc["createdAt"] = datetime.now(timezone.utc)
    result = await fixed_assets_col.insert_one(doc)
    doc["_id"] = result.inserted_id
    return serialize(doc)


@router.get("/api/fixed-assets")
async def list_fixed_assets(propertyId: str | None = None, user: dict = Depends(require_staff)):
    query: dict = {"orgId": user["orgId"]}
    if propertyId:
        query["propertyId"] = propertyId
    assets = await fixed_assets_col.find(query).sort("installDate", 1).to_list(length=1000)
    return {"assets": [serialize(a) for a in assets]}


@router.patch("/api/fixed-assets/{asset_id}")
async def update_fixed_asset(asset_id: str, payload: FixedAssetUpdate, user: dict = Depends(require_staff)):
    if not ObjectId.is_valid(asset_id):
        raise HTTPException(status_code=400, detail="Invalid asset ID")
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    result = await fixed_assets_col.find_one_and_update(
        {"_id": ObjectId(asset_id), "orgId": user["orgId"]}, {"$set": updates}, return_document=True
    )
    if not result:
        raise HTTPException(status_code=404, detail="Asset not found")
    return serialize(result)


@router.get("/api/fixed-assets/end-of-life")
async def assets_approaching_end_of_life(withinYears: float = 2.0, propertyId: str | None = None, user: dict = Depends(require_staff)):
    """The real, proactive-planning payoff of tracking installDate and
    expectedLifespanYears at all - assets whose expected replacement
    date falls within the given window from now (default 2 years),
    including anything already past it. Computed directly in Python
    from the two real stored fields, not a separate stored
    "end of life date" field that could drift out of sync if either
    input ever changed."""
    query: dict = {"orgId": user["orgId"]}
    if propertyId:
        query["propertyId"] = propertyId
    assets = await fixed_assets_col.find(query).to_list(length=1000)

    now = datetime.now(timezone.utc)
    results = []
    for asset in assets:
        install = asset["installDate"]
        if install.tzinfo is None:
            install = install.replace(tzinfo=timezone.utc)
        lifespan_seconds = asset["expectedLifespanYears"] * 365.25 * 86400
        end_of_life_ts = install.timestamp() + lifespan_seconds
        end_of_life_dt = datetime.fromtimestamp(end_of_life_ts, tz=timezone.utc)
        years_remaining = (end_of_life_ts - now.timestamp()) / (365.25 * 86400)

        if years_remaining <= withinYears:
            item = serialize(asset)
            item["endOfLifeDate"] = end_of_life_dt.isoformat()
            item["yearsRemaining"] = round(years_remaining, 2)
            item["pastEndOfLife"] = years_remaining < 0
            results.append(item)

    results.sort(key=lambda a: a["yearsRemaining"])
    return {"assets": results}


# ---------- Capital projects ----------

@router.post("/api/capital-projects")
async def create_capital_project(payload: CapitalProjectCreate, user: dict = Depends(require_staff)):
    doc = payload.model_dump()
    doc["orgId"] = user["orgId"]
    doc["targetDate"] = parse_date_utc(doc["targetDate"])
    doc["createdAt"] = datetime.now(timezone.utc)
    result = await capital_projects_col.insert_one(doc)
    doc["_id"] = result.inserted_id
    return serialize(doc)


@router.get("/api/capital-projects")
async def list_capital_projects(propertyId: str | None = None, status: str | None = None, user: dict = Depends(require_staff)):
    query: dict = {"orgId": user["orgId"]}
    if propertyId:
        query["propertyId"] = propertyId
    if status:
        query["status"] = status
    projects = await capital_projects_col.find(query).sort("targetDate", 1).to_list(length=1000)
    return {"projects": [serialize(p) for p in projects]}


@router.patch("/api/capital-projects/{project_id}")
async def update_capital_project(project_id: str, payload: CapitalProjectUpdate, user: dict = Depends(require_staff)):
    if not ObjectId.is_valid(project_id):
        raise HTTPException(status_code=400, detail="Invalid project ID")
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    if "targetDate" in updates:
        updates["targetDate"] = parse_date_utc(updates["targetDate"])
    result = await capital_projects_col.find_one_and_update(
        {"_id": ObjectId(project_id), "orgId": user["orgId"]}, {"$set": updates}, return_document=True
    )
    if not result:
        raise HTTPException(status_code=404, detail="Project not found")
    return serialize(result)
