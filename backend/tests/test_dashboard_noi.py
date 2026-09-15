"""
Dashboard NOI tests — confirms the real, honest calculation behind
each figure GET /api/dashboard/noi returns: actual collected revenue
minus actual categorized expenses for noiThisMonth, the reused (not
recomputed) revenueAtRisk figure for noiAtRisk, and a real trailing-
average projection for noiProjectedThisMonth that's honestly null
when there isn't yet enough real expense history to base one on.

NOTE on the "bank_lines" key used below: same real, pre-existing
conftest.py naming mismatch already documented elsewhere in this test
suite - bank_lines_col strips to "bank_lines" in the auto-patch
fixture, not this app's actual production collection name
("bank_statement_lines", per db.py).
"""
from datetime import datetime, timedelta, timezone

import pytest

from tests.conftest import auth_headers


@pytest.mark.asyncio
async def test_noi_this_month_is_collected_revenue_minus_categorized_expenses(client, org_a, patch_db_with_mock):
    now = datetime.now(timezone.utc)
    month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)

    # Real, collected revenue this month
    await patch_db_with_mock["payments"].insert_one({
        "orgId": org_a["orgId"], "propertyId": "p1", "unitId": "1A",
        "amountDue": 1200, "amountPaid": 1200, "paidDate": month_start + timedelta(days=2),
        "dueDate": month_start, "description": "Rent",
    })
    # A real, categorized expense this month
    await patch_db_with_mock["bank_lines"].insert_one({
        "orgId": org_a["orgId"], "propertyId": "p1", "date": month_start + timedelta(days=3),
        "description": "Plumber invoice", "amount": -300, "category": "maintenance", "matchedChargeId": None,
    })

    resp = await client.get("/api/dashboard/noi", headers=auth_headers(org_a))
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["revenueCollectedThisMonth"] == 1200
    assert data["expensesThisMonth"] == 300
    assert data["noiThisMonth"] == 900


@pytest.mark.asyncio
async def test_noi_ignores_uncategorized_bank_lines(client, org_a, patch_db_with_mock):
    """A bank line with no category (e.g. matched to a rent charge,
    not tagged as an expense) must never be counted as an expense -
    the same real convention routers/budgets.py's own report uses."""
    now = datetime.now(timezone.utc)
    month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    await patch_db_with_mock["bank_lines"].insert_one({
        "orgId": org_a["orgId"], "propertyId": "p1", "date": month_start + timedelta(days=1),
        "description": "Rent deposit", "amount": 1200, "category": None, "matchedChargeId": "some-charge-id",
    })

    resp = await client.get("/api/dashboard/noi", headers=auth_headers(org_a))
    data = resp.json()
    assert data["expensesThisMonth"] == 0


@pytest.mark.asyncio
async def test_noi_at_risk_matches_the_real_health_endpoint(client, org_a, patch_db_with_mock):
    """noiAtRisk must be the exact same real number
    /api/dashboard/health already computes - never a second,
    independently-drifting calculation of "at risk.\""""
    await patch_db_with_mock["properties"].insert_one({
        "orgId": org_a["orgId"], "name": "Vacant Test Bldg",
        "units": [{"unitId": "1", "status": "vacant", "rent": 950}],
    })

    health_resp = await client.get("/api/dashboard/health", headers=auth_headers(org_a))
    noi_resp = await client.get("/api/dashboard/noi", headers=auth_headers(org_a))

    assert noi_resp.json()["noiAtRisk"] == health_resp.json()["revenueAtRisk"]


@pytest.mark.asyncio
async def test_noi_projection_is_honestly_null_with_no_expense_history(client, org_a, patch_db_with_mock):
    """A brand-new org with zero real prior-month expense data must
    get an honest null projection, never a fabricated number standing
    in for missing real history."""
    resp = await client.get("/api/dashboard/noi", headers=auth_headers(org_a))
    data = resp.json()
    assert data["hasEnoughHistoryForProjection"] is False
    assert data["noiProjectedThisMonth"] is None
    assert data["projectedExpenses"] is None


@pytest.mark.asyncio
async def test_noi_projection_uses_real_trailing_expense_average(client, org_a, patch_db_with_mock):
    now = datetime.now(timezone.utc)
    month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    last_month_start = (month_start - timedelta(days=15)).replace(day=1)

    await patch_db_with_mock["properties"].insert_one({
        "orgId": org_a["orgId"], "name": "Projection Test Bldg",
        "units": [{"unitId": "1", "status": "occupied", "rent": 1000}],
    })
    await patch_db_with_mock["bank_lines"].insert_one({
        "orgId": org_a["orgId"], "propertyId": "p1", "date": last_month_start + timedelta(days=5),
        "description": "Last month's maintenance", "amount": -400, "category": "maintenance", "matchedChargeId": None,
    })

    resp = await client.get("/api/dashboard/noi", headers=auth_headers(org_a))
    data = resp.json()
    assert data["hasEnoughHistoryForProjection"] is True
    assert data["projectedExpenses"] == 400
    assert data["scheduledMonthlyRevenue"] == 1000
    assert data["noiProjectedThisMonth"] == 600


@pytest.mark.asyncio
async def test_noi_scoped_to_callers_own_org(client, org_a, org_b, patch_db_with_mock):
    now = datetime.now(timezone.utc)
    month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    await patch_db_with_mock["payments"].insert_one({
        "orgId": org_b["orgId"], "propertyId": "p1", "unitId": "1A",
        "amountDue": 5000, "amountPaid": 5000, "paidDate": month_start + timedelta(days=1),
        "dueDate": month_start, "description": "Org B rent",
    })

    resp = await client.get("/api/dashboard/noi", headers=auth_headers(org_a))
    assert resp.json()["revenueCollectedThisMonth"] == 0


@pytest.mark.asyncio
async def test_noi_rejects_unauthenticated_requests(client):
    resp = await client.get("/api/dashboard/noi")
    assert resp.status_code == 401
