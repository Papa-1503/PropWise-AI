"""
Rent-payment Stripe webhook tests — real regression protection for a
genuinely serious bug found during a comprehensive sweep: this webhook
(the one that confirms whether a real ACH rent payment actually
succeeded or failed) was calling .get() on a StripeObject, which
raises AttributeError - the same bug already fixed in
routers/billing.py's webhook, but this occurrence was missed until
this sweep. Since ACH payments are asynchronous (the whole reason this
webhook exists - see stripe_service.py's own docstring), every real
rent payment's actual outcome confirmation would have silently failed
to update the ledger.
"""
import hmac
import hashlib
import json
import time

import pytest

TEST_WEBHOOK_SECRET = "whsec_test_payment_webhook_secret"


def _sign_payload(payload: bytes, secret: str, timestamp: int | None = None) -> str:
    """Same real Stripe HMAC signature scheme as test_billing.py's own
    helper - see that file for the full explanation."""
    ts = timestamp or int(time.time())
    signed_payload = f"{ts}.{payload.decode()}"
    signature = hmac.new(secret.encode(), signed_payload.encode(), hashlib.sha256).hexdigest()
    return f"t={ts},v1={signature}"


@pytest.fixture(autouse=True)
def stripe_payment_webhook_secret(monkeypatch):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", TEST_WEBHOOK_SECRET)


@pytest.mark.asyncio
async def test_payment_succeeded_webhook_updates_the_real_charge(client, patch_db_with_mock):
    """The real, positive-path test: a validly-signed
    payment_intent.succeeded event must actually update amountPaid on
    the real charge it refers to - not just be accepted at the HTTP
    layer."""
    result = await patch_db_with_mock["payments"].insert_one({
        "propertyId": "p1", "unitId": "101", "amountDue": 1500.0, "amountPaid": 0.0,
        "stripePaymentIntentId": "pi_test_webhook_success",
        "orgId": "org_test",
    })

    payload = {
        "type": "payment_intent.succeeded",
        "data": {"object": {"id": "pi_test_webhook_success", "amount_received": 150000}},
    }
    payload_bytes = json.dumps(payload).encode()
    signature = _sign_payload(payload_bytes, TEST_WEBHOOK_SECRET)

    resp = await client.post(
        "/api/payments/stripe-webhook",
        content=payload_bytes,
        headers={"stripe-signature": signature, "content-type": "application/json"},
    )
    assert resp.status_code == 200, resp.text

    charge = await patch_db_with_mock["payments"].find_one({"_id": result.inserted_id})
    assert charge["amountPaid"] == 1500.0
    assert charge["paymentProcessingStatus"] == "succeeded"


@pytest.mark.asyncio
async def test_payment_failed_webhook_marks_charge_failed_without_touching_amount_paid(client, patch_db_with_mock):
    """A failed PaymentIntent never actually moved money, so
    amountPaid must be left untouched - only the status should
    reflect the real failure, for staff/resident follow-up."""
    result = await patch_db_with_mock["payments"].insert_one({
        "propertyId": "p1", "unitId": "101", "amountDue": 1500.0, "amountPaid": 0.0,
        "stripePaymentIntentId": "pi_test_webhook_failure",
        "orgId": "org_test",
    })

    payload = {
        "type": "payment_intent.payment_failed",
        "data": {"object": {"id": "pi_test_webhook_failure"}},
    }
    payload_bytes = json.dumps(payload).encode()
    signature = _sign_payload(payload_bytes, TEST_WEBHOOK_SECRET)

    resp = await client.post(
        "/api/payments/stripe-webhook",
        content=payload_bytes,
        headers={"stripe-signature": signature, "content-type": "application/json"},
    )
    assert resp.status_code == 200, resp.text

    charge = await patch_db_with_mock["payments"].find_one({"_id": result.inserted_id})
    assert charge["amountPaid"] == 0.0
    assert charge["paymentProcessingStatus"] == "failed"


@pytest.mark.asyncio
async def test_payment_webhook_rejects_forged_signature(client):
    payload_bytes = json.dumps({"type": "payment_intent.succeeded", "data": {"object": {}}}).encode()
    forged_signature = _sign_payload(payload_bytes, "wrong_secret_an_attacker_might_guess")
    resp = await client.post(
        "/api/payments/stripe-webhook",
        content=payload_bytes,
        headers={"stripe-signature": forged_signature, "content-type": "application/json"},
    )
    assert resp.status_code == 400
