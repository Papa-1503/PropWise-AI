"""
Predictive analytics (churn risk, seasonal vacancy forecasting).

GET /api/predictive/churn-risk?propertyId=      -> per-lease churn risk,
                                                    real weighted formula
GET /api/predictive/vacancy-forecast?propertyId=  -> real historical
                                                      vacancy pattern by
                                                      calendar month

Same "simple, transparent, explainable formula" philosophy already
used for every other score in this app (applicant screening, vendor
recommendation, ticket severity, tenant reliability) - never a
black-box statistical model, and every score comes with the real
factors that produced it, not just a bare number.
"""
from datetime import datetime, timezone
from collections import defaultdict

from fastapi import APIRouter, Depends

from db import leases_col, payments_col, tickets_col
from auth import require_staff
from routers.resident_360 import compute_reliability

router = APIRouter(prefix="/api/predictive", tags=["predictive-analytics"])


async def _churn_risk_for_lease(lease: dict, now: datetime) -> dict:
    payments = await payments_col.find({"leaseId": str(lease["_id"])}).to_list(length=500)
    reliability = compute_reliability(payments)
    reliability_score = reliability["score"] if reliability else 100

    end_date = lease.get("endDate")
    days_to_expiry = None
    expiry_risk = 0
    if isinstance(end_date, datetime):
        end_naive = end_date.replace(tzinfo=None) if end_date.tzinfo else end_date
        days_to_expiry = (end_naive - now.replace(tzinfo=None)).days
        if 0 <= days_to_expiry <= 60 and lease.get("renewalStatus") == "not_sent":
            expiry_risk = 40
        elif 0 <= days_to_expiry <= 60 and lease.get("renewalStatus") == "sent":
            expiry_risk = 20
        elif lease.get("renewalStatus") == "signed":
            expiry_risk = 0

    open_tickets = await tickets_col.count_documents({
        "propertyId": lease.get("propertyId"), "unitId": lease.get("unitId"), "status": {"$ne": "done"},
    })
    ticket_risk = min(30, open_tickets * 10)

    reliability_risk = round((100 - reliability_score) * 0.3) if reliability else 0

    total_risk = min(100, expiry_risk + ticket_risk + reliability_risk)

    return {
        "leaseId": str(lease["_id"]),
        "residentName": lease.get("residentName"),
        "unitId": lease.get("unitId"),
        "churnRiskScore": total_risk,
        "factors": {
            "daysToExpiry": days_to_expiry,
            "renewalStatus": lease.get("renewalStatus"),
            "paymentReliabilityScore": reliability_score if reliability else None,
            "openTicketCount": open_tickets,
        },
    }


@router.get("/churn-risk")
async def churn_risk(propertyId: str | None = None, user: dict = Depends(require_staff)):
    query = {"renewalStatus": {"$ne": "signed"}}
    if propertyId:
        query["propertyId"] = propertyId
    leases = await leases_col.find(query).to_list(length=1000)

    now = datetime.now(timezone.utc)
    results = [await _churn_risk_for_lease(lease, now) for lease in leases]
    results.sort(key=lambda r: r["churnRiskScore"], reverse=True)

    return {"leases": results}


@router.get("/vacancy-forecast")
async def vacancy_forecast(propertyId: str | None = None, user: dict = Depends(require_staff)):
    query = {}
    if propertyId:
        query["propertyId"] = propertyId
    leases = await leases_col.find(query).to_list(length=5000)

    month_counts = defaultdict(int)
    for lease in leases:
        end_date = lease.get("endDate")
        if isinstance(end_date, datetime):
            month_counts[end_date.month] += 1

    month_names = ["January", "February", "March", "April", "May", "June",
                   "July", "August", "September", "October", "November", "December"]
    rows = [{"month": month_names[m - 1], "monthNumber": m, "historicalLeaseEndCount": month_counts.get(m, 0)} for m in range(1, 13)]
    rows.sort(key=lambda r: r["historicalLeaseEndCount"], reverse=True)

    return {
        "note": "Real historical pattern of past lease end dates by month, not a statistical forecast - "
                "a human should weigh this alongside real local context (seasonal demand, local market "
                "conditions) this app has no way to know.",
        "rows": rows,
    }
