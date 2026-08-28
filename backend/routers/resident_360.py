"""
Resident and Unit "360" views (Priority 31) — read-only aggregation
endpoints that pull together everything already known about one
resident or one unit, using data that already exists in leases,
payments, maintenance_tickets, communications, and inspections. No new
collections — this is purely a convenience layer so staff don't have
to check five separate tabs to understand one situation.
"""
from fastapi import APIRouter, Depends, Query
from datetime import datetime, timezone

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
        return {"leases": [], "payments": [], "tickets": [], "communications": [], "reliability": None}

    or_query = {"$or": scope}
    payments = await payments_col.find(or_query).sort("dueDate", -1).to_list(length=200)
    tickets = await tickets_col.find(or_query).sort("createdAt", -1).to_list(length=100)
    comms = await communications_col.find(or_query).sort("createdAt", -1).to_list(length=100)

    return {
        "leases": leases,
        "payments": [serialize(p) for p in payments],
        "tickets": [serialize(t) for t in tickets],
        "communications": [serialize(c) for c in comms],
        "reliability": compute_reliability(payments),
    }


def compute_reliability(payments: list[dict]) -> dict | None:
    """A real, transparent payment-reliability score — same "simple
    weighted formula, not a statistical model" philosophy as the other
    scores built today (applicant screening, vendor recommendation,
    ticket severity). Only counts payments that have actually resolved
    one way or another (paid, or genuinely overdue with nothing paid) —
    a charge that's simply not due yet says nothing about reliability
    either way, so it's excluded rather than silently counted as
    "on time" by default.
    """
    # Naive, not timezone-aware — matching how Motor actually returns
    # dates read from MongoDB with this client (tz_aware isn't set in
    # db.py). Comparing a naive dueDate against an aware `now` raises
    # an uncaught TypeError in Python, crashing the whole request —
    # confirmed as the real cause of a live "Failed to fetch" error,
    # not assumed. The rest of this codebase already compares
    # Mongo-read dates against each other directly (e.g. dashboard.py's
    # paidDate > dueDate), so naive-vs-naive here is what's consistent.
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    on_time = 0
    late = 0
    missed = 0
    for p in payments:
        due = p.get("dueDate")
        paid = p.get("paidDate")
        if paid and due:
            if paid <= due:
                on_time += 1
            else:
                late += 1
        elif due and due < now and not paid:
            missed += 1
        # else: not yet due, or missing dates — not counted either way

    total = on_time + late + missed
    if total == 0:
        return None  # genuinely not enough history to say anything

    score = round(((on_time * 1.0) + (late * 0.4)) / total * 100)
    return {
        "score": score,
        "onTimeCount": on_time,
        "lateCount": late,
        "missedCount": missed,
        "totalCount": total,
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
