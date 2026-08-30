"""
Global command-palette search (Ctrl+K), genuinely cross-app rather than
a per-page search like PropertyManagement's unit search. Also fulfils
the separate, previously-flagged "Add global search/command navigation"
item from the navigation-simplification priorities.

Deliberately simple: case-insensitive regex match on a handful of real,
already-indexed-in-spirit text fields per collection, capped to a small
result count per type. Not a full-text search engine — a command
palette needs to feel instant, not exhaustive.

Searches leases (name, unit, resident phone), tickets (title, unit),
and leads (name, email, phone). Vendors were considered but skipped:
there's no standalone vendor page to navigate a result to (vendors
only appear nested inside VendorAssignment during ticket assignment),
so a vendor search result would have nowhere sensible to land.
"""

from fastapi import APIRouter, Depends

from db import leases_col, tickets_col, leads_col
from auth import require_staff

router = APIRouter(prefix="/api/search", tags=["search"])

RESULT_LIMIT_PER_TYPE = 5


@router.get("")
async def global_search(q: str, propertyId: str | None = None, user: dict = Depends(require_staff)):
    if not q or len(q.strip()) < 2:
        return {"results": []}

    regex = {"$regex": q.strip(), "$options": "i"}
    scope = {"propertyId": propertyId} if propertyId else {}
    results = []

    async for l in leases_col.find({**scope, "$or": [{"residentName": regex}, {"unitId": regex}, {"residentPhone": regex}]}).limit(RESULT_LIMIT_PER_TYPE):
        results.append({
            "type": "lease",
            "id": str(l["_id"]),
            "title": l.get("residentName", "Unnamed resident"),
            "subtitle": f"Unit {l.get('unitId', '?')} — lease",
            "navigateTo": "leases",
        })

    async for t in tickets_col.find({**scope, "$or": [{"title": regex}, {"unitId": regex}]}).limit(RESULT_LIMIT_PER_TYPE):
        results.append({
            "type": "ticket",
            "id": str(t["_id"]),
            "title": t.get("title", "Untitled ticket"),
            "subtitle": f"Unit {t.get('unitId', '?')} — maintenance",
            "navigateTo": "maintenance",
        })

    async for ld in leads_col.find({**scope, "$or": [{"name": regex}, {"email": regex}, {"phone": regex}]}).limit(RESULT_LIMIT_PER_TYPE):
        results.append({
            "type": "lead",
            "id": str(ld["_id"]),
            "title": ld.get("name", "Unnamed lead"),
            "subtitle": f"{ld.get('email', '')} — lead",
            "navigateTo": "leads",
        })

    return {"results": results}
