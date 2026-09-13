"""
Billing security tests — the highest-stakes area in this app to get
wrong, since it involves real money. Two real properties verified
here:
  1. The webhook endpoint genuinely verifies Stripe's HMAC signature -
     a forged 'subscription active' event must be rejected, and a
     validly-signed one must be accepted and actually update the org.
  2. Checkout/Portal are genuinely restricted to the org owner - a
     regular staff member (not the owner) must never be able to
     change what the organization pays.
"""
import hmac
import hashlib
import json
import time

import pytest

from conftest import auth_headers

TEST_WEBHOOK_SECRET = "whsec_test_secret_for_signature_tests_only"


def _sign_payload(payload: bytes, secret: str, timestamp: int | None = None) -> str:
    """Manually constructs a real Stripe webhook signature header,
    using the exact scheme Stripe's own SDK verifies against
    (documented, stable behavior - not a private implementation
    detail): HMAC-SHA256 over "{timestamp}.{payload}", formatted as
    Stripe's own Stripe-Signature header."""
    ts = timestamp or int(time.time())
    signed_payload = f"{ts}.{payload.decode()}"
    signature = hmac.new(secret.encode(), signed_payload.encode(), hashlib.sha256).hexdigest()
    return f"t={ts},v1={signature}"


@pytest.fixture(autouse=True)
def stripe_billing_webhook_secret(monkeypatch):
    monkeypatch.setenv("STRIPE_BILLING_WEBHOOK_SECRET", TEST_WEBHOOK_SECRET)


@pytest.mark.asyncio
async def test_webhook_rejects_unsigned_request(client):
    payload = {"type": "checkout.session.completed", "data": {"object": {}}}
    resp = await client.post("/api/billing/webhook", content=json.dumps(payload))
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_webhook_rejects_forged_signature(client):
    """A request signed with the WRONG secret (simulating an attacker
    who doesn't know the real one) must be rejected, not processed as
    if it were real."""
    payload_bytes = json.dumps({"type": "checkout.session.completed", "data": {"object": {}}}).encode()
    forged_signature = _sign_payload(payload_bytes, "wrong_secret_an_attacker_might_guess")
    resp = await client.post(
        "/api/billing/webhook",
        content=payload_bytes,
        headers={"stripe-signature": forged_signature, "content-type": "application/json"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_webhook_accepts_validly_signed_event_and_upgrades_org(client, org_a, patch_db_with_mock):
    """The real, positive-path test: a genuinely validly-signed
    checkout.session.completed event must actually flip the org's
    plan to 'pro' - not just be accepted at the HTTP layer."""
    from bson import ObjectId
    org_object_id = ObjectId(org_a["orgId"])
    await patch_db_with_mock["organizations"].update_one(
        {"_id": org_object_id}, {"$set": {"stripeCustomerId": "cus_test_123"}}
    )

    payload = {
        "type": "checkout.session.completed",
        "data": {"object": {"customer": "cus_test_123", "subscription": "sub_test_456"}},
    }
    payload_bytes = json.dumps(payload).encode()
    valid_signature = _sign_payload(payload_bytes, TEST_WEBHOOK_SECRET)

    resp = await client.post(
        "/api/billing/webhook",
        content=payload_bytes,
        headers={"stripe-signature": valid_signature, "content-type": "application/json"},
    )
    assert resp.status_code == 200, resp.text

    org = await patch_db_with_mock["organizations"].find_one({"_id": org_object_id})
    assert org["plan"] == "pro"
    assert org["active"] is True
    assert org["stripeSubscriptionId"] == "sub_test_456"


@pytest.mark.asyncio
async def test_webhook_deactivates_org_on_subscription_canceled(client, org_a, patch_db_with_mock):
    from bson import ObjectId
    org_object_id = ObjectId(org_a["orgId"])
    await patch_db_with_mock["organizations"].update_one(
        {"_id": org_object_id}, {"$set": {"stripeCustomerId": "cus_test_789", "plan": "pro", "active": True}}
    )

    payload = {
        "type": "customer.subscription.deleted",
        "data": {"object": {"customer": "cus_test_789", "status": "canceled"}},
    }
    payload_bytes = json.dumps(payload).encode()
    valid_signature = _sign_payload(payload_bytes, TEST_WEBHOOK_SECRET)

    resp = await client.post(
        "/api/billing/webhook",
        content=payload_bytes,
        headers={"stripe-signature": valid_signature, "content-type": "application/json"},
    )
    assert resp.status_code == 200, resp.text

    org = await patch_db_with_mock["organizations"].find_one({"_id": org_object_id})
    assert org["active"] is False


@pytest.mark.asyncio
async def test_non_owner_staff_cannot_reach_checkout(client, org_a):
    """org_a's signup account IS the owner (isOrgOwner set by the real
    signup flow) - this test needs a SECOND staff account on the same
    org that is explicitly NOT the owner, matching the real shape of
    a team with more than one staff member. register-staff is real,
    already-authenticated staff creating another staff account in
    their own org - no separate invite-code step exists for this."""
    register_resp = await client.post(
        "/api/auth/register-staff",
        json={"name": "Team Mate", "email": "teammate@example.com", "password": "teammatepass123"},
        headers=auth_headers(org_a),
    )
    assert register_resp.status_code == 200, register_resp.text
    teammate_token = register_resp.json()["accessToken"]

    resp = await client.post(
        "/api/billing/checkout",
        json={"tier": "starter", "successUrl": "https://example.com/ok", "cancelUrl": "https://example.com/cancel"},
        headers={"Authorization": f"Bearer {teammate_token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_checkout_rejects_invalid_tier(client, org_a):
    """The 3 real tiers are a closed set - anything else must fail
    validation, not silently fall through to some default price."""
    resp = await client.post(
        "/api/billing/checkout",
        json={"tier": "not-a-real-tier", "successUrl": "https://example.com/ok", "cancelUrl": "https://example.com/cancel"},
        headers=auth_headers(org_a),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_tiers_endpoint_recommends_based_on_real_unit_count(client, org_a, patch_db_with_mock):
    """A real, live unit count drives the recommendation - not a
    stored, staleable counter. Verifies all 3 recommendation bands."""
    # No properties yet - should recommend starter (0 units)
    resp = await client.get("/api/billing/tiers", headers=auth_headers(org_a))
    assert resp.status_code == 200
    data = resp.json()
    assert data["yourUnitCount"] == 0
    assert data["recommendedTier"] == "starter"
    assert len(data["tiers"]) == 3
    assert {t["id"] for t in data["tiers"]} == {"starter", "growth", "pro"}

    # Add a property with 40 units - should now recommend growth
    await patch_db_with_mock["properties"].insert_one({
        "name": "Big Complex", "orgId": org_a["orgId"],
        "units": [{"unitId": str(i)} for i in range(40)],
    })
    resp2 = await client.get("/api/billing/tiers", headers=auth_headers(org_a))
    data2 = resp2.json()
    assert data2["yourUnitCount"] == 40
    assert data2["recommendedTier"] == "growth"

    # Add another property pushing total past 100 - should recommend pro
    await patch_db_with_mock["properties"].insert_one({
        "name": "Huge Portfolio", "orgId": org_a["orgId"],
        "units": [{"unitId": str(i)} for i in range(70)],
    })
    resp3 = await client.get("/api/billing/tiers", headers=auth_headers(org_a))
    data3 = resp3.json()
    assert data3["yourUnitCount"] == 110
    assert data3["recommendedTier"] == "pro"


@pytest.mark.asyncio
async def test_webhook_sets_billing_tier_from_checkout_metadata(client, org_a, patch_db_with_mock):
    """The real, primary path: tier chosen at checkout is read back
    from Stripe's own metadata and stored on the org."""
    from bson import ObjectId
    org_object_id = ObjectId(org_a["orgId"])
    await patch_db_with_mock["organizations"].update_one(
        {"_id": org_object_id}, {"$set": {"stripeCustomerId": "cus_test_tier_1"}}
    )

    payload = {
        "type": "checkout.session.completed",
        "data": {"object": {
            "customer": "cus_test_tier_1", "subscription": "sub_test_tier_1",
            "metadata": {"tier": "growth"},
        }},
    }
    payload_bytes = json.dumps(payload).encode()
    valid_signature = _sign_payload(payload_bytes, TEST_WEBHOOK_SECRET)

    resp = await client.post(
        "/api/billing/webhook", content=payload_bytes,
        headers={"stripe-signature": valid_signature, "content-type": "application/json"},
    )
    assert resp.status_code == 200, resp.text

    org = await patch_db_with_mock["organizations"].find_one({"_id": org_object_id})
    assert org["billingTier"] == "growth"


@pytest.mark.asyncio
async def test_webhook_self_heals_tier_from_subscription_price_id(client, org_a, patch_db_with_mock, monkeypatch):
    """The real, self-healing path: a plan change made through the
    Stripe Customer Portal never carries checkout metadata at all -
    this must still correctly update billingTier by matching the
    subscription's actual current Price ID against this app's own
    configured tier env vars."""
    monkeypatch.setenv("STRIPE_PRICE_ID_PRO", "price_real_pro_tier_id")

    from bson import ObjectId
    org_object_id = ObjectId(org_a["orgId"])
    await patch_db_with_mock["organizations"].update_one(
        {"_id": org_object_id}, {"$set": {"stripeCustomerId": "cus_test_tier_2", "billingTier": "starter", "plan": "pro", "active": True}}
    )

    payload = {
        "type": "customer.subscription.updated",
        "data": {"object": {
            "customer": "cus_test_tier_2", "status": "active",
            "items": {"data": [{"price": {"id": "price_real_pro_tier_id"}}]},
        }},
    }
    payload_bytes = json.dumps(payload).encode()
    valid_signature = _sign_payload(payload_bytes, TEST_WEBHOOK_SECRET)

    resp = await client.post(
        "/api/billing/webhook", content=payload_bytes,
        headers={"stripe-signature": valid_signature, "content-type": "application/json"},
    )
    assert resp.status_code == 200, resp.text

    org = await patch_db_with_mock["organizations"].find_one({"_id": org_object_id})
    assert org["billingTier"] == "pro"  # correctly upgraded from "starter", even with no checkout metadata at all
