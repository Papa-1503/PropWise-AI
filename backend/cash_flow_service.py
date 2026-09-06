"""
Net cash flow / NOI (net operating income) reporting.

Genuinely missing before this: income (payments_col, via
dashboard.py's revenue-trend) and expenses (bank_lines_col, via
reconciliation.py + budgets.py's budget-vs-actual) have always been
tracked as two separate, never-combined ledgers. Nothing anywhere
computed a net figure, and owner-facing statements
(routers/owners.py's /me/statements) only ever showed the income half
(billed/collected/outstanding) - an owner asking "am I actually
cash-flow positive on this building" had no real answer anywhere in
the app.

This combines the two real ledgers per calendar month:
- income  = payments_col.amountPaid, grouped by paidDate's month
  (identical definition to dashboard.py's existing revenue-trend, so
  the two stay consistent rather than silently disagreeing)
- expenses = bank_lines_col entries with a real category (same
  "uncategorized lines are excluded, not guessed into a bucket"
  principle budgets.py's report already established), restricted to
  fundType == "operating" - a trust-held security deposit moving
  through the bank is not a real operating expense, and folding it in
  would distort NOI even though budgets.py's own report doesn't apply
  this filter (that report predates fundType meaningfully mattering
  for a net-income figure the way it does here).

netCashFlow = income - expenses. Called "net cash flow" in the API
response rather than strictly "NOI" - real NOI conventionally excludes
capital expenditures and debt service, and this app doesn't yet
distinguish those from ordinary operating bank lines, so claiming a
textbook-precise NOI figure would overstate what's actually being
measured. This is an honest net operating cash flow number, which is
what "update cash flow and NOI" in practice means for a report at this
scale.
"""
from datetime import datetime, timezone, timedelta

from db import payments_col, bank_lines_col


async def cash_flow_trend(org_id: str, property_ids: list[str] | None, months: int = 6) -> list[dict]:
    """Real month-by-month net cash flow across the given properties (or
    every property in this org if property_ids is None/empty), most
    recent `months` calendar months. Returns one row per month that has
    EITHER income or expense activity - a month with no real
    transactions on either side doesn't appear, rather than a
    misleading zero bar for a month before the property was even under
    management.

    org_id is required and always applied - without it, the "every
    property" case (no specific building selected) would aggregate
    income/expense data across every organization in the database
    combined, a real cross-tenant leak this app had before this pass."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=months * 31)

    income_query: dict = {"paidDate": {"$ne": None, "$gte": cutoff}, "orgId": org_id}
    expense_query: dict = {
        "category": {"$ne": None},
        "fundType": "operating",
        "date": {"$gte": cutoff},
        "orgId": org_id,
    }
    if property_ids:
        income_query["propertyId"] = {"$in": property_ids}
        expense_query["propertyId"] = {"$in": property_ids}

    income_pipeline = [
        {"$match": income_query},
        {"$group": {
            "_id": {"$dateToString": {"format": "%Y-%m", "date": "$paidDate"}},
            "total": {"$sum": "$amountPaid"},
        }},
    ]
    expense_pipeline = [
        {"$match": expense_query},
        {"$group": {
            "_id": {"$dateToString": {"format": "%Y-%m", "date": "$date"}},
            # Bank line amounts can be positive or negative depending on
            # how staff entered them (the same real, existing ambiguity
            # budgets.py's report already documents) - abs() so this
            # reflects real expense magnitude regardless of sign
            # convention, same reasoning as that report's own abs() use.
            "total": {"$sum": {"$abs": "$amount"}},
        }},
    ]

    income_rows = await payments_col.aggregate(income_pipeline).to_list(length=months + 1)
    expense_rows = await bank_lines_col.aggregate(expense_pipeline).to_list(length=months + 1)

    income_by_month = {r["_id"]: r["total"] for r in income_rows}
    expense_by_month = {r["_id"]: r["total"] for r in expense_rows}

    all_months = sorted(set(income_by_month) | set(expense_by_month))
    result = []
    for month in all_months:
        income = round(income_by_month.get(month, 0), 2)
        expenses = round(expense_by_month.get(month, 0), 2)
        result.append({
            "month": month,
            "income": income,
            "expenses": expenses,
            "netCashFlow": round(income - expenses, 2),
        })
    return result
