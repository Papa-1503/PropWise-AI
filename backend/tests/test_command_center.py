"""
Command Center tests — confirms the daily priority digest aggregates
real data from 4 real sources (renewal risk, delinquency, urgent
maintenance, pending AI actions), never fabricates a dollar figure
for a source that doesn't have one, and never returns an item type
when there's genuinely nothing to show for it (no empty/placeholder
entries).
"""
from datetime import datetime, timedelta, timezone

import pytest

from tests.conftest import auth_headers


@pytest.mark.asyncio
async def test_empty_portfolio_returns_no_items(client, org_a, patch_db_with_mock):
    resp = await client.get("/api/dashboard/command-center", headers=auth_headers(org_a))
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["items"] == []
    assert data["totalQuantifiedImpact"] == 0


@pytest.mark.asyncio
async def test_delinquent_accounts_appear_with_real_dollar_figure(client, org_a, patch_db_with_mock):
    now = datetime.now(timezone.utc)
    await patch_db_with_mock["payments"].insert_one({
        "orgId": org_a["orgId"], "propertyId": "p1", "unitId": "1A",
        "amountDue": 1500, "amountPaid": 0, "dueDate": now - timedelta(days=10),
        "description": "Rent",
    })

    resp = await client.get("/api/dashboard/command-center", headers=auth_headers(org_a))
    data = resp.json()
    delinquent_item = next((i for i in data["items"] if i["type"] == "delinquent"), None)
    assert delinquent_item is not None
    assert delinquent_item["dollarImpact"] == 1500
    assert delinquent_item["count"] == 1
    assert delinquent_item["link"] == "/app/payments"
    assert data["totalQuantifiedImpact"] == 1500


@pytest.mark.asyncio
async def test_urgent_maintenance_never_fabricates_a_dollar_figure(client, org_a, patch_db_with_mock):
    """No honest cost-of-inaction model exists for maintenance -
    dollarImpact must stay null, never a guessed number."""
    await patch_db_with_mock["tickets"].insert_one({
        "orgId": org_a["orgId"], "propertyId": "p1", "unitId": "1A",
        "title": "No heat", "priority": "urgent", "status": "open",
        "category": "hvac", "source": "resident", "createdAt": datetime.now(timezone.utc),
    })

    resp = await client.get("/api/dashboard/command-center", headers=auth_headers(org_a))
    data = resp.json()
    maint_item = next((i for i in data["items"] if i["type"] == "maintenance_urgent"), None)
    assert maint_item is not None
    assert maint_item["dollarImpact"] is None
    assert maint_item["count"] == 1
    # A null-impact item must never be counted into the real total.
    assert data["totalQuantifiedImpact"] == 0


@pytest.mark.asyncio
async def test_done_and_non_urgent_tickets_are_excluded(client, org_a, patch_db_with_mock):
    now = datetime.now(timezone.utc)
    await patch_db_with_mock["tickets"].insert_one({
        "orgId": org_a["orgId"], "propertyId": "p1", "unitId": "1A",
        "title": "Fixed leak", "priority": "urgent", "status": "done",
        "category": "plumbing", "source": "resident", "createdAt": now,
    })
    await patch_db_with_mock["tickets"].insert_one({
        "orgId": org_a["orgId"], "propertyId": "p1", "unitId": "1B",
        "title": "Squeaky door", "priority": "normal", "status": "open",
        "category": "general", "source": "resident", "createdAt": now,
    })

    resp = await client.get("/api/dashboard/command-center", headers=auth_headers(org_a))
    data = resp.json()
    assert not any(i["type"] == "maintenance_urgent" for i in data["items"])


@pytest.mark.asyncio
async def test_pending_ai_actions_sum_real_estimated_value(client, org_a, patch_db_with_mock):
    now = datetime.now(timezone.utc)
    await patch_db_with_mock["ai_actions"].insert_one({
        "orgId": org_a["orgId"], "propertyId": "p1", "type": "collections_reminder",
        "title": "Suggested action A", "priority": "medium", "rationale": "r",
        "projectedOutcome": "o", "estimatedValue": 500, "affectedUnitIds": [],
        "confidence": 70, "riskLevel": "low", "plannedSteps": [], "status": "suggested",
        "createdAt": now,
    })
    await patch_db_with_mock["ai_actions"].insert_one({
        "orgId": org_a["orgId"], "propertyId": "p1", "type": "rent_adjustment",
        "title": "Suggested action B", "priority": "low", "rationale": "r",
        "projectedOutcome": "o", "estimatedValue": 300, "affectedUnitIds": [],
        "confidence": 60, "riskLevel": "low", "plannedSteps": [], "status": "suggested",
        "createdAt": now,
    })
    # An already-approved action must never be counted as "pending".
    await patch_db_with_mock["ai_actions"].insert_one({
        "orgId": org_a["orgId"], "propertyId": "p1", "type": "rent_adjustment",
        "title": "Already approved", "priority": "low", "rationale": "r",
        "projectedOutcome": "o", "estimatedValue": 9999, "affectedUnitIds": [],
        "confidence": 60, "riskLevel": "low", "plannedSteps": [], "status": "approved",
        "createdAt": now,
    })

    resp = await client.get("/api/dashboard/command-center", headers=auth_headers(org_a))
    data = resp.json()
    action_item = next((i for i in data["items"] if i["type"] == "pending_ai_action"), None)
    assert action_item is not None
    assert action_item["count"] == 2
    assert action_item["dollarImpact"] == 800


@pytest.mark.asyncio
async def test_items_sorted_by_dollar_impact_descending(client, org_a, patch_db_with_mock):
    now = datetime.now(timezone.utc)
    await patch_db_with_mock["payments"].insert_one({
        "orgId": org_a["orgId"], "propertyId": "p1", "unitId": "1A",
        "amountDue": 500, "amountPaid": 0, "dueDate": now - timedelta(days=5),
        "description": "Rent",
    })
    await patch_db_with_mock["ai_actions"].insert_one({
        "orgId": org_a["orgId"], "propertyId": "p1", "type": "collections_reminder",
        "title": "High-value action", "priority": "high", "rationale": "r",
        "projectedOutcome": "o", "estimatedValue": 5000, "affectedUnitIds": [],
        "confidence": 80, "riskLevel": "low", "plannedSteps": [], "status": "suggested",
        "createdAt": now,
    })

    resp = await client.get("/api/dashboard/command-center", headers=auth_headers(org_a))
    data = resp.json()
    impacts = [i["dollarImpact"] for i in data["items"] if i["dollarImpact"] is not None]
    assert impacts == sorted(impacts, reverse=True)


@pytest.mark.asyncio
async def test_scoped_to_callers_own_org(client, org_a, org_b, patch_db_with_mock):
    now = datetime.now(timezone.utc)
    await patch_db_with_mock["payments"].insert_one({
        "orgId": org_b["orgId"], "propertyId": "p1", "unitId": "1A",
        "amountDue": 9999, "amountPaid": 0, "dueDate": now - timedelta(days=5),
        "description": "Org B rent",
    })

    resp = await client.get("/api/dashboard/command-center", headers=auth_headers(org_a))
    data = resp.json()
    assert data["items"] == []


@pytest.mark.asyncio
async def test_rejects_unauthenticated_requests(client):
    resp = await client.get("/api/dashboard/command-center")
    assert resp.status_code == 401
