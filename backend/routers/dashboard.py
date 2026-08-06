"""
Dashboard stats endpoint.

GET /api/dashboard/stats?propertyId=

Runs real aggregation queries against properties/leases/tickets/inspections
instead of returning hardcoded numbers — mirrors the stat cards in the
Dashboard screen (occupancy, revenue, vacancies, open tickets, inspections due).
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends

from db import properties_col, leases_col, tickets_col, inspections_col, ai_actions_col, payments_col, leads_col
from auth import require_staff

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/health")
async def get_portfolio_health(propertyId: str | None = None, user: dict = Depends(require_staff)):
    """
    Matches the 'Portfolio Health Score' header in the new dashboard design.
    Unlike the AI Actions confidence scores, everything here is plain
    arithmetic over live data — no LLM involved, so it's fully reproducible.
    """
    prop_filter = {"_id": propertyId} if propertyId else {}
    properties = await properties_col.find(prop_filter).to_list(length=500)

    total_units = 0
    vacant_units = 0
    revenue_at_risk = 0.0

    for p in properties:
        for u in p.get("units", []):
            total_units += 1
            if u.get("status") == "vacant":
                vacant_units += 1
                revenue_at_risk += u.get("rent", 0)

    ticket_query = {"propertyId": propertyId} if propertyId else {}
    critical_work_orders = await tickets_col.count_documents(
        {**ticket_query, "status": {"$ne": "done"}, "priority": "urgent"}
    )

    cutoff = datetime.now(timezone.utc) + timedelta(days=60)
    lease_query = {**ticket_query, "endDate": {"$lte": cutoff}}
    lease_renewals_needed = await leases_col.count_documents(lease_query)

    # unsigned renewals also count toward revenue at risk
    at_risk_leases = await leases_col.find(
        {**lease_query, "renewalStatus": {"$ne": "signed"}}
    ).to_list(length=200)
    revenue_at_risk += sum(l.get("rent", 0) for l in at_risk_leases)

    # delinquent balances are real revenue at risk too
    now = datetime.now(timezone.utc)
    delinquent_charges = await payments_col.find(
        {**ticket_query, "dueDate": {"$lt": now}}
    ).to_list(length=1000)
    delinquent_balance = sum(
        c["amountDue"] - c.get("amountPaid", 0)
        for c in delinquent_charges
        if c.get("amountPaid", 0) < c.get("amountDue", 0)
    )
    revenue_at_risk += delinquent_balance

    occupancy_pct = ((total_units - vacant_units) / total_units * 100) if total_units else 100

    # simple, transparent composite score — tune weights as you see fit;
    # documented here so it's never a mystery number
    delinquent_count = sum(
        1 for c in delinquent_charges if c.get("amountPaid", 0) < c.get("amountDue", 0)
    )

    score = 100
    score -= min(30, vacant_units * 2)          # vacancy drag
    score -= min(20, critical_work_orders * 5)   # urgent maintenance drag
    score -= min(20, lease_renewals_needed * 1)  # renewal exposure drag
    score -= min(15, delinquent_count * 3)       # delinquency drag
    score = max(0, round(score))

    return {
        "healthScore": score,
        "revenueAtRisk": round(revenue_at_risk, 2),
        "vacancies": vacant_units,
        "leaseRenewalsNeeded": lease_renewals_needed,
        "criticalWorkOrders": critical_work_orders,
        "occupancyPct": round(occupancy_pct, 1),
        "delinquentAccounts": delinquent_count,
        "delinquentBalance": round(delinquent_balance, 2),
    }


@router.get("/workforce")
async def get_workforce_stats(propertyId: str | None = None, days: int = 30, user: dict = Depends(require_staff)):
    """
    Backs the 'AI Workforce' panel. Only reports numbers we actually track:

    - MaintenanceAI: real, computed from the tickets collection
    - OperationsAI: real, computed from the ai_actions collection
    - LeasingAI: NOT tracked — there's no leads/tours/applications data
      anywhere in this system yet. Returned as null rather than a fake 0.
    - CollectionsAI: NOT tracked — no payment/collections module exists.
      Returned as null for the same reason.

    Wire up a leasing CRM and a payments/collections module before these
    two can report real numbers — don't backfill them with guesses.
    """
    prop_filter = {"propertyId": propertyId} if propertyId else {}
    since = datetime.now(timezone.utc) - timedelta(days=days)

    tickets_created = await tickets_col.count_documents(
        {**prop_filter, "createdAt": {"$gte": since}}
    )
    auto_created = await tickets_col.count_documents(
        {**prop_filter, "createdAt": {"$gte": since}, "source": "inspection"}
    )

    actions_suggested = await ai_actions_col.count_documents(
        {**prop_filter, "createdAt": {"$gte": since}}
    )
    actions_approved = await ai_actions_col.count_documents(
        {
            **prop_filter,
            "createdAt": {"$gte": since},
            "status": {"$in": ["approved", "executing", "completed"]},
        }
    )
    completed_actions = await ai_actions_col.find(
        {**prop_filter, "createdAt": {"$gte": since}, "status": "completed"}
    ).to_list(length=500)
    revenue_protected = sum(a.get("estimatedValue") or 0 for a in completed_actions)

    # CollectionsAI — now real, computed from the payments ledger.
    # "Residents contacted" counts distinct units that received a
    # collections_reminder email in the window (from completed ai_actions).
    # "Recovered revenue" sums payments recorded in the window for charges
    # that were past due at the time they were paid — i.e. actually
    # collected after becoming delinquent, not just on-time rent.
    completed_reminders = await ai_actions_col.find(
        {**prop_filter, "createdAt": {"$gte": since}, "status": "completed", "type": "collections_reminder"}
    ).to_list(length=200)
    residents_contacted = sum(len(a.get("executionResult", {}).get("sent", [])) for a in completed_reminders)

    recently_paid = await payments_col.find(
        {**prop_filter, "paidDate": {"$gte": since}, "amountPaid": {"$gt": 0}}
    ).to_list(length=1000)
    recovered_revenue = sum(
        p["amountPaid"] for p in recently_paid
        if p.get("dueDate") and p.get("paidDate") and p["paidDate"] > p["dueDate"]
    )

    return {
        "windowDays": days,
        "maintenanceAI": {
            "ticketsCreated": tickets_created,
            "autoCreatedFromInspections": auto_created,
            "failuresPrevented": None,
            "tracked": True,
        },
        "operationsAI": {
            "actionsSuggested": actions_suggested,
            "actionsApproved": actions_approved,
            "revenueProtected": round(revenue_protected, 2),
            "tracked": True,
        },
        "leasingAI": {
            "leadsProcessed": None,
            "toursScheduled": None,
            "applications": None,
            "leasesSigned": None,
            "tracked": False,
            "note": "No leasing/CRM data source connected yet.",
        },
        "collectionsAI": {
            "residentsContacted": residents_contacted,
            "recoveredRevenue": round(recovered_revenue, 2),
            "tracked": True,
        },
    }


@router.get("/maintenance-trends")
async def get_maintenance_trends(propertyId: str | None = None, user: dict = Depends(require_staff)):
    """
    Real trend detection: compares ticket counts per category in the last
    30 days against the 30 days before that. Flags a category as
    'increasing' only if both (a) the count went up and (b) there are
    enough tickets for the comparison to mean something (avoids flagging
    '1 ticket became 2 tickets' as a trend).

    This replaces the kind of alert your mockup showed ("HVAC Repairs
    Increasing") with one computed from real ticket data instead of a
    scripted example.
    """
    prop_filter = {"propertyId": propertyId} if propertyId else {}
    now = datetime.now(timezone.utc)
    recent_start = now - timedelta(days=30)
    prior_start = now - timedelta(days=60)

    pipeline_recent = [
        {"$match": {**prop_filter, "createdAt": {"$gte": recent_start, "$lte": now}}},
        {"$group": {"_id": "$category", "count": {"$sum": 1}}},
    ]
    pipeline_prior = [
        {"$match": {**prop_filter, "createdAt": {"$gte": prior_start, "$lt": recent_start}}},
        {"$group": {"_id": "$category", "count": {"$sum": 1}}},
    ]
    recent_counts = {d["_id"]: d["count"] async for d in tickets_col.aggregate(pipeline_recent)}
    prior_counts = {d["_id"]: d["count"] async for d in tickets_col.aggregate(pipeline_prior)}

    trends = []
    for category, recent_count in recent_counts.items():
        prior_count = prior_counts.get(category, 0)
        # require at least 3 recent tickets so a 1->2 blip doesn't count as a "trend"
        if recent_count >= 3 and recent_count > prior_count:
            pct_change = round(((recent_count - prior_count) / prior_count) * 100) if prior_count else None
            trends.append({
                "category": category,
                "recentCount": recent_count,
                "priorCount": prior_count,
                "pctChange": pct_change,  # null when prior_count was 0 — can't compute % from zero
            })

    trends.sort(key=lambda t: t["recentCount"] - t["priorCount"], reverse=True)
    return {"trends": trends, "windowDays": 30}


@router.post("/maintenance-trends/{category}/schedule-inspection")
async def schedule_preventive_inspection(category: str, propertyId: str | None = None, user: dict = Depends(require_staff)):
    """
    Creates an AI Action record (type: maintenance_followup) suggesting a
    preventive inspection sweep for a category showing a real upward trend.
    No LLM call here — the trigger and confidence are both computed
    directly from the trend data itself.
    """
    prop_filter = {"propertyId": propertyId} if propertyId else {}
    now = datetime.now(timezone.utc)
    recent_start = now - timedelta(days=30)
    recent_count = await tickets_col.count_documents(
        {**prop_filter, "category": category, "createdAt": {"$gte": recent_start}}
    )
    if recent_count < 3:
        raise HTTPException(status_code=400, detail="Not enough recent tickets in this category to justify scheduling")

    doc = {
        "propertyId": propertyId,
        "type": "maintenance_followup",
        "title": f"Schedule preventive inspection sweep — {category}",
        "priority": "medium",
        "rationale": f"{recent_count} {category} tickets opened in the last 30 days, above the threshold for a proactive check.",
        "projectedOutcome": "Reduced reactive repair volume",
        "estimatedValue": None,
        "affectedUnitIds": [],
        "confidence": min(95, 50 + recent_count * 5),  # simple, documented, deterministic — not LLM-guessed
        "riskLevel": "low",
        "plannedSteps": [f"Identify units with recent {category} tickets", "Schedule inspection sweep", "Log findings as new tickets if needed"],
        "status": "suggested",
        "createdAt": now,
    }
    result = await ai_actions_col.insert_one(doc)
    doc["_id"] = result.inserted_id
    doc["id"] = str(doc.pop("_id"))
    for f in ("createdAt",):
        if isinstance(doc.get(f), datetime):
            doc[f] = doc[f].isoformat()
    return doc


@router.get("/stats")
async def get_dashboard_stats(propertyId: str | None = None, user: dict = Depends(require_staff)):
    prop_filter = {"_id": propertyId} if propertyId else {}

    properties = await properties_col.find(prop_filter).to_list(length=500)

    total_units = 0
    occupied_units = 0
    vacant_units = 0
    monthly_revenue = 0.0

    for p in properties:
        for u in p.get("units", []):
            total_units += 1
            if u.get("status") == "occupied":
                occupied_units += 1
                monthly_revenue += u.get("rent", 0)
            elif u.get("status") == "vacant":
                vacant_units += 1

    occupancy_pct = round((occupied_units / total_units) * 100, 1) if total_units else 0

    ticket_query = {"propertyId": propertyId} if propertyId else {}
    open_tickets = await tickets_col.count_documents({**ticket_query, "status": {"$ne": "done"}})
    urgent_tickets = await tickets_col.count_documents(
        {**ticket_query, "status": {"$ne": "done"}, "priority": "urgent"}
    )

    # "Inspections due" — properties/units without an inspection in the last 365 days.
    # Simplified here as: units with zero inspections in the last year.
    one_year_ago = datetime.now(timezone.utc) - timedelta(days=365)
    recent_inspection_unit_ids = set(
        await inspections_col.distinct(
            "unitId", {**ticket_query, "createdAt": {"$gte": one_year_ago}}
        )
    )
    all_unit_ids = {u.get("unitId") for p in properties for u in p.get("units", [])}
    inspections_due = len(all_unit_ids - recent_inspection_unit_ids)

    return {
        "occupancyPct": occupancy_pct,
        "monthlyRevenue": round(monthly_revenue, 2),
        "vacantUnits": vacant_units,
        "openTickets": open_tickets,
        "urgentTickets": urgent_tickets,
        "inspectionsDue": inspections_due,
    }
