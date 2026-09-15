"""
Workforce panel drill-down tests — confirms GET /api/dashboard/workforce
returns the real, itemized breakdown behind its two AI-attributed
headline dollar figures (revenueProtected, recoveredRevenue), not just
the totals. Added directly in response to a real product review
concern: a sophisticated operator seeing "$160,880 revenue protected"
reasonably asks how that number was calculated before trusting it -
these breakdowns are the honest, verifiable answer.
"""
from datetime import datetime, timedelta, timezone

import pytest

from tests.conftest import auth_headers


@pytest.mark.asyncio
async def test_revenue_protected_breakdown_lists_the_real_completed_actions(client, org_a, patch_db_with_mock):
    now = datetime.now(timezone.utc)
    await patch_db_with_mock["ai_actions"].insert_one({
        "orgId": org_a["orgId"], "propertyId": "p1", "type": "renewal_campaign",
        "title": "Renewal incentive offered to Unit 4B", "priority": "medium", "rationale": "r",
        "projectedOutcome": "o", "estimatedValue": 1200, "affectedUnitIds": ["4B"],
        "confidence": 80, "riskLevel": "low", "plannedSteps": [], "status": "completed",
        "createdAt": now - timedelta(days=1),
    })

    resp = await client.get("/api/dashboard/workforce", headers=auth_headers(org_a))
    assert resp.status_code == 200, resp.text
    data = resp.json()
    breakdown = data["operationsAI"]["revenueProtectedBreakdown"]
    assert len(breakdown) == 1
    assert breakdown[0]["title"] == "Renewal incentive offered to Unit 4B"
    assert breakdown[0]["estimatedValue"] == 1200
    assert breakdown[0]["affectedUnitIds"] == ["4B"]
    assert data["operationsAI"]["revenueProtected"] == 1200


@pytest.mark.asyncio
async def test_recovered_revenue_breakdown_lists_real_late_payments_with_days_late(client, org_a, patch_db_with_mock):
    now = datetime.now(timezone.utc)
    due_date = now - timedelta(days=10)
    paid_date = now - timedelta(days=2)
    await patch_db_with_mock["payments"].insert_one({
        "orgId": org_a["orgId"], "propertyId": "p1", "unitId": "2C",
        "amountDue": 900, "amountPaid": 900, "dueDate": due_date, "paidDate": paid_date,
        "description": "Rent",
    })

    resp = await client.get("/api/dashboard/workforce", headers=auth_headers(org_a))
    data = resp.json()
    breakdown = data["collectionsAI"]["recoveredRevenueBreakdown"]
    assert len(breakdown) == 1
    assert breakdown[0]["unitId"] == "2C"
    assert breakdown[0]["amountPaid"] == 900
    assert breakdown[0]["daysLate"] == 8
    assert data["collectionsAI"]["recoveredRevenue"] == 900


@pytest.mark.asyncio
async def test_on_time_payment_never_appears_in_recovered_breakdown(client, org_a, patch_db_with_mock):
    """A payment made ON or BEFORE its due date is not a real
    "recovery" - it must never inflate the breakdown or the total."""
    now = datetime.now(timezone.utc)
    due_date = now + timedelta(days=5)
    await patch_db_with_mock["payments"].insert_one({
        "orgId": org_a["orgId"], "propertyId": "p1", "unitId": "3D",
        "amountDue": 1000, "amountPaid": 1000, "dueDate": due_date, "paidDate": now,
        "description": "Rent, paid early",
    })

    resp = await client.get("/api/dashboard/workforce", headers=auth_headers(org_a))
    data = resp.json()
    assert data["collectionsAI"]["recoveredRevenueBreakdown"] == []
    assert data["collectionsAI"]["recoveredRevenue"] == 0
