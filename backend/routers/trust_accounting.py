"""
Trust accounting (Phase 5).

*** NOT A SUBSTITUTE FOR REAL TRUST ACCOUNTING COMPLIANCE. *** Most
states require security deposits and other resident/owner-held funds
to be kept in a real, legally segregated trust/escrow bank account,
separate from a property manager's own operating funds - specific
rules (reconciliation cadence, permitted uses, reporting) vary by
state and require a licensed accountant/attorney to get right. This
app has no way to verify actual bank-level segregation (whether the
real money is genuinely sitting in a real separate account) - it can
only track how STAFF CLASSIFY each bank line entry (trust vs.
operating, BankLineCreate.fundType) and flag patterns worth a human's
attention. Never presented as compliance verification.

GET /api/trust-accounting/balance      -> real trust-fund balance per
                                           property, computed from
                                           real bank lines tagged
                                           fundType="trust"
GET /api/trust-accounting/commingling-check
                                        -> flags apparent commingling
                                           patterns for human review

MULTI-TENANCY: both real gaps this pass closes - previously, viewing
either endpoint with no propertyId filter (the natural "show me
everything" default) aggregated trust-fund balances across every
organization in the database combined, a genuine cross-tenant
financial data leak given these are real trust/escrow fund figures.
"""
from fastapi import APIRouter, Depends

from db import bank_lines_col
from auth import require_staff

router = APIRouter(prefix="/api/trust-accounting", tags=["trust-accounting"])

DISCLAIMER = (
    "This is a real tracking tool based on how staff classify each bank line entry - it does "
    "NOT verify actual bank-level fund segregation and is not a substitute for state-specific "
    "trust accounting compliance, which requires a licensed accountant or attorney."
)


@router.get("/balance")
async def trust_balance(propertyId: str | None = None, user: dict = Depends(require_staff)):
    query: dict = {"fundType": "trust", "orgId": user["orgId"]}
    if propertyId:
        query["propertyId"] = propertyId

    pipeline = [
        {"$match": query},
        {"$group": {"_id": "$propertyId", "trustBalance": {"$sum": "$amount"}, "lineCount": {"$sum": 1}}},
        {"$sort": {"trustBalance": -1}},
    ]
    results = await bank_lines_col.aggregate(pipeline).to_list(length=200)

    rows = [{"propertyId": r["_id"], "trustBalance": round(r["trustBalance"], 2), "lineCount": r["lineCount"]} for r in results]
    return {"disclaimer": DISCLAIMER, "rows": rows}


@router.get("/commingling-check")
async def commingling_check(propertyId: str | None = None, user: dict = Depends(require_staff)):
    """Real, honest pattern-flagging, not a compliance verdict - a
    negative trust balance is the single clearest real red flag this
    app can actually detect from its own data: it means more was
    classified as paid out of trust than was ever classified as
    coming in, which is either a real problem or a real
    misclassification - either way, worth a human looking at
    specifically, not something to silently let sit."""
    query: dict = {"fundType": "trust", "orgId": user["orgId"]}
    if propertyId:
        query["propertyId"] = propertyId

    pipeline = [
        {"$match": query},
        {"$group": {"_id": "$propertyId", "trustBalance": {"$sum": "$amount"}}},
        {"$match": {"trustBalance": {"$lt": 0}}},
        {"$sort": {"trustBalance": 1}},
    ]
    results = await bank_lines_col.aggregate(pipeline).to_list(length=200)

    flags = [
        {
            "propertyId": r["_id"],
            "trustBalance": round(r["trustBalance"], 2),
            "concern": "Negative trust balance - more classified as paid from trust than received into it. Review for misclassification or a real fund shortfall.",
        }
        for r in results
    ]
    return {"disclaimer": DISCLAIMER, "flags": flags, "flaggedCount": len(flags)}
