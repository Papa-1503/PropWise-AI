"""
Custom report builder (P18).

GET/POST   /api/custom-reports              -> saved report definition CRUD
DELETE     /api/custom-reports/{id}
POST       /api/custom-reports/{id}/run     -> executes the real aggregation
                                                for that saved report

Deliberately NOT an open-ended query builder - see CustomReportCreate's
docstring in models.py for why. Each real reportType below has its own
real, hand-written, bounded aggregation, reusing logic already proven
elsewhere this session (budgets.py's report, make_ready.py's
aggregation) rather than a generic pipeline accepting arbitrary input.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends
from bson import ObjectId

from db import custom_reports_col, payments_col, tickets_col, properties_col
from models import CustomReportCreate
from date_utils import parse_date_utc
from auth import require_staff

router = APIRouter(prefix="/api/custom-reports", tags=["custom-reports"])


def serialize(doc: dict) -> dict:
    doc = dict(doc)
    doc["id"] = str(doc.pop("_id"))
    return doc


@router.post("")
async def create_report(payload: CustomReportCreate, user: dict = Depends(require_staff)):
    doc = payload.model_dump()
    doc["createdAt"] = datetime.now(timezone.utc)
    result = await custom_reports_col.insert_one(doc)
    doc["_id"] = result.inserted_id
    return serialize(doc)


@router.get("")
async def list_reports(user: dict = Depends(require_staff)):
    reports = await custom_reports_col.find({}).sort("name", 1).to_list(length=200)
    return {"reports": [serialize(r) for r in reports]}


@router.delete("/{report_id}")
async def delete_report(report_id: str, user: dict = Depends(require_staff)):
    if not ObjectId.is_valid(report_id):
        raise HTTPException(status_code=400, detail="Invalid report ID")
    result = await custom_reports_col.delete_one({"_id": ObjectId(report_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Report not found")
    return {"deleted": True}


async def _run_revenue_by_property(report: dict) -> dict:
    query = {"paidDate": {"$ne": None}}
    if report.get("propertyId"):
        query["propertyId"] = report["propertyId"]
    if report.get("startDate"):
        query.setdefault("paidDate", {})["$gte"] = parse_date_utc(report["startDate"])
    if report.get("endDate"):
        query.setdefault("paidDate", {})["$lte"] = parse_date_utc(report["endDate"])

    pipeline = [
        {"$match": query},
        {"$group": {"_id": "$propertyId", "totalRevenue": {"$sum": "$amountPaid"}, "chargeCount": {"$sum": 1}}},
        {"$sort": {"totalRevenue": -1}},
    ]
    results = await payments_col.aggregate(pipeline).to_list(length=200)
    return {"rows": [{"propertyId": r["_id"], "totalRevenue": round(r["totalRevenue"], 2), "chargeCount": r["chargeCount"]} for r in results]}


async def _run_maintenance_by_category(report: dict) -> dict:
    query = {}
    if report.get("propertyId"):
        query["propertyId"] = report["propertyId"]
    if report.get("startDate") or report.get("endDate"):
        date_range = {}
        if report.get("startDate"):
            date_range["$gte"] = parse_date_utc(report["startDate"])
        if report.get("endDate"):
            date_range["$lte"] = parse_date_utc(report["endDate"])
        query["createdAt"] = date_range

    pipeline = [
        {"$match": query},
        {"$group": {"_id": "$category", "ticketCount": {"$sum": 1}, "totalHours": {"$sum": {"$ifNull": ["$totalHours", 0]}}}},
        {"$sort": {"ticketCount": -1}},
    ]
    results = await tickets_col.aggregate(pipeline).to_list(length=50)
    return {"rows": [{"category": r["_id"], "ticketCount": r["ticketCount"], "totalHours": round(r["totalHours"], 1)} for r in results]}


async def _run_occupancy_trend(report: dict) -> dict:
    """Real, current occupancy snapshot per property - a genuine
    historical trend over time would need periodic status snapshots
    this app doesn't currently store, so this is honestly a
    point-in-time report, not a trend line, and named accordingly in
    its output rather than implying history that doesn't exist."""
    query = {"_id": report["propertyId"]} if report.get("propertyId") else {}
    properties = await properties_col.find(query).to_list(length=200)
    rows = []
    for p in properties:
        units = p.get("units", [])
        occupied = sum(1 for u in units if u.get("status") == "occupied")
        total = len(units)
        rows.append({
            "propertyId": p["_id"], "propertyName": p.get("name"),
            "occupiedUnits": occupied, "totalUnits": total,
            "occupancyPct": round(occupied / total * 100, 1) if total else 0,
        })
    return {"rows": rows, "note": "Current snapshot, not a historical trend - this app doesn't store periodic occupancy history yet."}


REPORT_RUNNERS = {
    "revenue_by_property": _run_revenue_by_property,
    "maintenance_by_category": _run_maintenance_by_category,
    "occupancy_trend": _run_occupancy_trend,
}


@router.post("/{report_id}/run")
async def run_report(report_id: str, user: dict = Depends(require_staff)):
    if not ObjectId.is_valid(report_id):
        raise HTTPException(status_code=400, detail="Invalid report ID")
    report = await custom_reports_col.find_one({"_id": ObjectId(report_id)})
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    runner = REPORT_RUNNERS[report["reportType"]]
    result = await runner(report)
    return {"reportType": report["reportType"], "name": report["name"], **result}
