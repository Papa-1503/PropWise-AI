"""
Resident and Unit "360" views (Priority 31) — read-only aggregation
endpoints that pull together everything already known about one
resident or one unit, using data that already exists in leases,
payments, maintenance_tickets, communications, and inspections. No new
collections — this is purely a convenience layer so staff don't have
to check five separate tabs to understand one situation.
"""
from fastapi import APIRouter, Depends, Query

from db import leases_col, payments_col, tickets_col, communications_col, inspections_col
from auth import require_staff

router = APIRouter(prefix="/api", tags=["360-views"])


def serialize(doc: dict) -> dict:
    doc = dict(doc)
    doc["id"] = str(doc.pop("_id"))
    return doc


@router.get("/residents/360")
async def resident_360(email: str = Query(...), user: dict = Depends(require_staff)):
    leases = await leases_col.find({"residentEmail": email}).sort("startDate", -1).to_list(length=50)
    leases = [serialize(l) for l in leases]

    # Scope payments/tickets/communications to the properties+units this
    # resident has actually had a lease on — a resident could plausibly
    # have moved between units over time, so this isn't just their
    # single most-recent lease's unit.
    scope = [{"propertyId": l["propertyId"], "unitId": l["unitId"]} for l in leases]
    if not scope:
        return {"leases": [], "payments": [], "tickets": [], "communications": []}

    or_query = {"$or": scope}
    payments = await payments_col.find(or_query).sort("dueDate", -1).to_list(length=200)
    tickets = await tickets_col.find(or_query).sort("createdAt", -1).to_list(length=100)
    comms = await communications_col.find(or_query).sort("createdAt", -1).to_list(length=100)

    return {
        "leases": leases,
        "payments": [serialize(p) for p in payments],
        "tickets": [serialize(t) for t in tickets],
        "communications": [serialize(c) for c in comms],
    }


@router.get("/units/360")
async def unit_360(
    propertyId: str = Query(...),
    unitId: str = Query(...),
    user: dict = Depends(require_staff),
):
    query = {"propertyId": propertyId, "unitId": unitId}

    leases = await leases_col.find(query).sort("startDate", -1).to_list(length=50)
    payments = await payments_col.find(query).sort("dueDate", -1).to_list(length=200)
    tickets = await tickets_col.find(query).sort("createdAt", -1).to_list(length=100)
    inspections = await inspections_col.find(query).sort("createdAt", -1).to_list(length=50)

    return {
        "leases": [serialize(l) for l in leases],
        "payments": [serialize(p) for p in payments],
        "tickets": [serialize(t) for t in tickets],
        "inspections": [serialize(i) for i in inspections],
    }
