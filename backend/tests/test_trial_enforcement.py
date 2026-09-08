"""
Trial enforcement tests — real regression protection for
auth.py's _enforce_trial_status, the single change that gates
staff/owner access across the entire app once a trial expires.

Three real risks this protects against:
  1. A genuinely expired trial must actually block staff/owner access
     (a 402), not silently let it through.
  2. Tenants must NEVER be blocked by their landlord's billing state -
     get_current_user (what every tenant-facing endpoint uses) is
     completely untouched by this check.
  3. Billing endpoints themselves must remain reachable even when
     blocked, or an organization whose trial expired would have no
     way to ever fix that.
"""
from datetime import datetime, timedelta, timezone

import pytest

from conftest import auth_headers


async def _expire_trial(patch_db_with_mock, org_id: str):
    """Directly backdates an org's trialEndsAt into the past - the
    real, fast way to put an org into the 'expired' state a test
    needs, without waiting 14 real days."""
    from bson import ObjectId
    await patch_db_with_mock["organizations"].update_one(
        {"_id": ObjectId(org_id)},
        {"$set": {"trialEndsAt": datetime.now(timezone.utc) - timedelta(days=1)}},
    )


@pytest.mark.asyncio
async def test_active_trial_is_not_blocked(client, org_a):
    """Sanity check: a genuinely fresh trial (org_a's real 14-day
    trial from signup) must never be blocked."""
    resp = await client.get("/api/properties", headers=auth_headers(org_a))
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_expired_trial_blocks_staff_access(client, org_a, patch_db_with_mock):
    await _expire_trial(patch_db_with_mock, org_a["orgId"])
    resp = await client.get("/api/properties", headers=auth_headers(org_a))
    assert resp.status_code == 402
    assert "trial" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_expired_trial_still_allows_billing_status_check(client, org_a, patch_db_with_mock):
    """The real reason billing.py's _require_org_owner uses
    get_current_user directly instead of require_staff: an
    organization whose trial expired must always still be able to
    reach the one place that lets them subscribe."""
    await _expire_trial(patch_db_with_mock, org_a["orgId"])
    resp = await client.get("/api/billing/status", headers=auth_headers(org_a))
    assert resp.status_code == 200
    assert resp.json()["blocked"] is True


@pytest.mark.asyncio
async def test_paid_org_is_never_blocked_even_with_stale_trial_date(client, org_a, patch_db_with_mock):
    """Real scenario: an org converted to 'pro' via the Stripe webhook
    weeks ago, but its old trialEndsAt field is still sitting there in
    the past (nothing ever clears it). Confirms _enforce_trial_status
    checks plan == 'trial' first, not just the date."""
    await _expire_trial(patch_db_with_mock, org_a["orgId"])
    from bson import ObjectId
    await patch_db_with_mock["organizations"].update_one(
        {"_id": ObjectId(org_a["orgId"])},
        {"$set": {"plan": "pro", "active": True}},
    )
    resp = await client.get("/api/properties", headers=auth_headers(org_a))
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_internal_plan_org_is_never_blocked(client, org_a, patch_db_with_mock):
    """This app's own real portfolio (plan='internal', see main.py's
    migration) must never be trial-gated, regardless of trialEndsAt."""
    await _expire_trial(patch_db_with_mock, org_a["orgId"])
    from bson import ObjectId
    await patch_db_with_mock["organizations"].update_one(
        {"_id": ObjectId(org_a["orgId"])},
        {"$set": {"plan": "internal"}},
    )
    resp = await client.get("/api/properties", headers=auth_headers(org_a))
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_tenant_is_never_blocked_by_org_trial_expiration(client, org_a, patch_db_with_mock):
    """The real, load-bearing boundary: a resident must never be
    locked out of maintenance/payments because their landlord's
    organization is behind on billing. Creates a genuine tenant
    account (via a lease + invite code, the app's real activation
    flow) and confirms it's untouched by the org's expired trial."""
    from bson import ObjectId

    prop_resp = await client.post(
        "/api/properties",
        json={"name": "Trial Test Bldg", "address": "1 Test St", "units": [
            {"unitId": "1", "status": "vacant", "rent": 1200},
        ]},
        headers=auth_headers(org_a),
    )
    property_id = prop_resp.json()["id"]

    now = datetime.now(timezone.utc)
    lease_resp = await client.post(
        "/api/leases",
        json={
            "propertyId": property_id, "unitId": "1", "residentName": "Test Tenant",
            "residentEmail": "tenant@example.com",
            "startDate": now.isoformat(), "endDate": (now + timedelta(days=365)).isoformat(),
            "rent": 1200,
        },
        headers=auth_headers(org_a),
    )
    invite_code = lease_resp.json()["inviteCode"]

    register_resp = await client.post("/api/auth/register", json={
        "inviteCode": invite_code, "name": "Test Tenant",
        "email": "tenant@example.com", "password": "tenantpass123",
    })
    assert register_resp.status_code == 200, register_resp.text
    tenant_token = register_resp.json()["accessToken"]

    await _expire_trial(patch_db_with_mock, org_a["orgId"])

    resp = await client.get(
        "/api/leases/mine", headers={"Authorization": f"Bearer {tenant_token}"}
    )
    assert resp.status_code == 200, resp.text
