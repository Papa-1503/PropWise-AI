"""
Budget vs. actual tracking, per property/category/month.

POST   /api/budgets                          -> set a budget line (one property,
                                                 one category, one month)
GET    /api/budgets?propertyId=&period=      -> list budget lines
PATCH  /api/budgets/{budget_id}              -> change a budgeted amount
GET    /api/budgets/report?propertyId=&period= -> the actual comparison: budgeted
                                                 vs. real spending for that
                                                 property+month, by category

"Actual" spending comes from bank_lines_col (routers/reconciliation.py) -
real bank statement lines staff have already entered, not a second,
synthetic ledger invented just for this feature. category on
BankLineCreate is new (added alongside these changes) since bank lines
previously had no way to say what kind of expense a line represented,
which real budget-vs-actual comparison fundamentally needs.

Deliberately excludes income (rent, deposits) from the comparison -
budget-vs-actual in a property-management context means operating
expense categories (maintenance, utilities, insurance, etc.) against
their budgeted amounts, not comparing income lines against an
expense budget, which wouldn't mean anything. A bank line without a
category is treated as unclassified and excluded from the report
rather than silently attributed to any one category - an uncategorized
line skewing a category's actual spend would be a worse outcome than
it simply not appearing in the comparison yet.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends
from bson import ObjectId

from db import budgets_col, bank_lines_col
from models import BudgetCreate, BudgetUpdate
from auth import require_staff
from audit_service import log_action

router = APIRouter(prefix="/api/budgets", tags=["budgets"])


def serialize(doc: dict) -> dict:
    doc = dict(doc)
    doc["id"] = str(doc.pop("_id"))
    return doc


@router.post("")
async def create_budget(payload: BudgetCreate, user: dict = Depends(require_staff)):
    doc = payload.model_dump()
    doc["createdAt"] = datetime.now(timezone.utc)
    try:
        result = await budgets_col.insert_one(doc)
    except Exception as exc:
        # The unique index on (propertyId, category, period) is what
        # actually enforces "one budget per property+category+month" -
        # a duplicate key error here means exactly that constraint was
        # violated, surfaced as a clear 409 rather than a raw 500.
        if "duplicate key" in str(exc).lower():
            raise HTTPException(
                status_code=409,
                detail=f"A budget for {payload.category} in {payload.period} already exists for this property. Use PATCH to update it.",
            )
        raise
    doc["_id"] = result.inserted_id

    await log_action(
        actor_id=str(user["id"]), actor_email=user.get("email", ""),
        action="budget_created", target_type="budget", target_id=str(result.inserted_id),
        details={"propertyId": payload.propertyId, "category": payload.category, "period": payload.period, "budgetedAmount": payload.budgetedAmount},
    )

    return serialize(doc)


@router.get("")
async def list_budgets(propertyId: str | None = None, period: str | None = None, user: dict = Depends(require_staff)):
    query = {}
    if propertyId:
        query["propertyId"] = propertyId
    if period:
        query["period"] = period
    cursor = budgets_col.find(query).sort([("period", -1), ("category", 1)])
    budgets = await cursor.to_list(length=500)
    return {"budgets": [serialize(b) for b in budgets]}


@router.patch("/{budget_id}")
async def update_budget(budget_id: str, payload: BudgetUpdate, user: dict = Depends(require_staff)):
    if not ObjectId.is_valid(budget_id):
        raise HTTPException(status_code=400, detail="Invalid budget ID")
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    result = await budgets_col.find_one_and_update(
        {"_id": ObjectId(budget_id)}, {"$set": updates}, return_document=True
    )
    if not result:
        raise HTTPException(status_code=404, detail="Budget not found")

    await log_action(
        actor_id=str(user["id"]), actor_email=user.get("email", ""),
        action="budget_updated", target_type="budget", target_id=budget_id,
        details=updates,
    )

    return serialize(result)


@router.get("/report")
async def budget_vs_actual_report(propertyId: str, period: str, user: dict = Depends(require_staff)):
    """The real comparison, per category: budgeted amount vs. actual
    spending from real bank lines dated within that calendar month,
    for that property. variance = budgeted - actual (positive means
    under budget, negative means over)."""
    budgets = await budgets_col.find({"propertyId": propertyId, "period": period}).to_list(length=200)

    year, month = period.split("-")
    month_start = datetime(int(year), int(month), 1, tzinfo=timezone.utc)
    month_end = datetime(int(year) + (1 if month == "12" else 0), (1 if month == "12" else int(month) + 1), 1, tzinfo=timezone.utc)

    bank_lines = await bank_lines_col.find({
        "propertyId": propertyId,
        "date": {"$gte": month_start, "$lt": month_end},
        "category": {"$ne": None},
    }).to_list(length=2000)

    actual_by_category = {}
    for line in bank_lines:
        cat = line.get("category")
        # Bank line amounts can be positive or negative depending on how
        # staff entered them (a real, existing ambiguity in
        # reconciliation.py this report doesn't try to silently resolve)
        # - abs() here so a budget-vs-actual comparison reflects real
        # spending magnitude regardless of sign convention, rather than
        # a negative expense line partially cancelling out a positive
        # one in the same category and understating actual spend.
        actual_by_category[cat] = actual_by_category.get(cat, 0) + abs(line.get("amount", 0))

    rows = []
    all_categories = {b["category"] for b in budgets} | set(actual_by_category.keys())
    for category in sorted(all_categories):
        budgeted = next((b["budgetedAmount"] for b in budgets if b["category"] == category), 0)
        actual = actual_by_category.get(category, 0)
        rows.append({
            "category": category,
            "budgeted": round(budgeted, 2),
            "actual": round(actual, 2),
            "variance": round(budgeted - actual, 2),
        })

    return {
        "propertyId": propertyId,
        "period": period,
        "categories": rows,
        "totalBudgeted": round(sum(r["budgeted"] for r in rows), 2),
        "totalActual": round(sum(r["actual"] for r in rows), 2),
    }
