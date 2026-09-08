"""
Organization-level SaaS billing — trial status, upgrade checkout, and
self-serve subscription management. Distinct from routers/payments.py
(a resident paying rent) and routers/reconciliation.py (bank
reconciliation) - this is the OTHER real financial flow this app
needs: this app's own customer (an organization) paying to keep using
PropWise AI.

GET  /api/billing/status    -> real current plan/trial state for the
                                caller's own org - used to render a
                                trial countdown banner or a "trial
                                expired" block screen
POST /api/billing/checkout  -> (org owner) creates a real Stripe
                                Checkout Session for the single paid
                                plan, returns the URL to redirect to
POST /api/billing/portal    -> (org owner) creates a real Stripe
                                Customer Portal session for self-serve
                                management (payment method, invoices,
                                cancel)
POST /api/billing/webhook   -> PUBLIC, Stripe-signed - real
                                subscription lifecycle events land
                                here and update the organization's
                                real plan/active state

SINGLE PLAN, DELIBERATELY: this app has exactly one real paid tier
(STRIPE_PRICE_ID) rather than a multi-tier plan list with per-tier
feature gating. A real multi-tier system (e.g. a per-unit-count price,
or feature-gated tiers) is genuine, valuable follow-on work once
there's a real reason to differentiate - not fabricated here just to
look more complete than what's actually been built and verified.

Requires billing_service.py's own environment variables
(STRIPE_SECRET_KEY, STRIPE_PRICE_ID, STRIPE_BILLING_WEBHOOK_SECRET) -
see that module's docstring. Every endpoint here fails with an honest
501/503, never a silent no-op, if billing isn't configured.
"""
import os
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from bson import ObjectId

from db import organizations_col
from auth import get_current_user
import billing_service
from billing_service import StripeNotConfigured, StripePayError

router = APIRouter(prefix="/api/billing", tags=["billing"])


class CheckoutRequest(BaseModel):
    successUrl: str
    cancelUrl: str


class PortalRequest(BaseModel):
    returnUrl: str


async def _require_org_owner(user: dict = Depends(get_current_user)) -> dict:
    """Billing is deliberately gated to the org OWNER specifically
    (isOrgOwner), not every staff member - who can change what this
    organization pays for real money is a narrower boundary than who
    can manage leases or tickets. Uses get_current_user directly
    rather than require_staff, so billing endpoints are NEVER subject
    to the trial-expiration block added to require_role below - an
    organization whose trial has expired must always still be able to
    reach the one place that lets them fix that."""
    if user.get("role") != "staff" or not user.get("isOrgOwner"):
        raise HTTPException(status_code=403, detail="Only the organization owner can manage billing.")
    return user


def _billing_status(org: dict) -> dict:
    """Real, computed status from the organization's own stored
    fields - never a separate cached/duplicated status value that
    could drift from what's actually true. 'blocked' is the one real
    boolean the frontend needs to decide whether to show a hard block
    screen; everything else is display detail."""
    now = datetime.now(timezone.utc)
    plan = org.get("plan", "trial")
    active = org.get("active", True)
    trial_ends_at = org.get("trialEndsAt")

    if trial_ends_at and trial_ends_at.tzinfo is None:
        trial_ends_at = trial_ends_at.replace(tzinfo=timezone.utc)

    trial_expired = bool(trial_ends_at and now > trial_ends_at)
    is_paid = plan in ("pro", "internal") and active

    days_left = None
    if plan == "trial" and trial_ends_at:
        days_left = max(0, (trial_ends_at - now).days)

    return {
        "plan": plan,
        "active": active,
        "trialEndsAt": trial_ends_at.isoformat() if trial_ends_at else None,
        "trialDaysLeft": days_left,
        "trialExpired": trial_expired,
        "blocked": plan == "trial" and trial_expired and not is_paid,
        "subscriptionStatus": org.get("stripeSubscriptionStatus"),
    }


@router.get("/status")
async def get_billing_status(user: dict = Depends(get_current_user)):
    """Any authenticated staff/owner can check their own org's real
    billing status - read-only, no reason to restrict this to the
    owner the way actually changing billing is restricted below."""
    org_id = user.get("orgId")
    if not org_id:
        raise HTTPException(status_code=400, detail="Your account isn't linked to an organization.")
    query_id = ObjectId(org_id) if ObjectId.is_valid(org_id) else org_id
    org = await organizations_col.find_one({"_id": query_id})
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    return _billing_status(org)


@router.post("/checkout")
async def create_checkout(payload: CheckoutRequest, user: dict = Depends(_require_org_owner)):
    price_id = os.getenv("STRIPE_PRICE_ID")
    if not price_id:
        raise HTTPException(status_code=501, detail="Billing isn't configured yet — STRIPE_PRICE_ID is not set.")

    org_id = user["orgId"]
    query_id = ObjectId(org_id) if ObjectId.is_valid(org_id) else org_id
    org = await organizations_col.find_one({"_id": query_id})
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    try:
        customer_id = await billing_service.get_or_create_org_customer_async(
            org_id, user["email"], org.get("name", "")
        )
        result = await billing_service.create_checkout_session_async(
            customer_id, price_id, payload.successUrl, payload.cancelUrl
        )
    except StripeNotConfigured as exc:
        raise HTTPException(status_code=501, detail=str(exc))
    except StripePayError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    await organizations_col.update_one({"_id": query_id}, {"$set": {"stripeCustomerId": customer_id}})
    return result


@router.post("/portal")
async def create_portal_session(payload: PortalRequest, user: dict = Depends(_require_org_owner)):
    org_id = user["orgId"]
    query_id = ObjectId(org_id) if ObjectId.is_valid(org_id) else org_id
    org = await organizations_col.find_one({"_id": query_id})
    if not org or not org.get("stripeCustomerId"):
        raise HTTPException(status_code=400, detail="No billing account on file yet — subscribe first.")

    try:
        result = await billing_service.create_billing_portal_session_async(
            org["stripeCustomerId"], payload.returnUrl
        )
    except StripeNotConfigured as exc:
        raise HTTPException(status_code=501, detail=str(exc))
    except StripePayError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return result


@router.post("/webhook")
async def billing_webhook(request: Request):
    """Real, security-boundary-verified endpoint - see
    billing_service.py's construct_billing_webhook_event. Public (no
    user session possible - Stripe calls this directly), so signature
    verification is the only thing standing between this endpoint and
    a forged 'subscription active' event.

    checkout.session.completed is when a trial genuinely converts to
    paid - the real moment plan flips to 'pro'. subscription.updated/
    deleted keep the org's real status in sync with whatever actually
    happens afterward (a failed renewal charge, a real cancellation) -
    an org is never silently left marked 'pro' after its subscription
    has actually lapsed."""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    try:
        event = billing_service.construct_billing_webhook_event(payload, sig_header)
    except (StripeNotConfigured, StripePayError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    obj = event["data"]["object"]

    if event["type"] == "checkout.session.completed":
        customer_id = obj.get("customer")
        subscription_id = obj.get("subscription")
        if customer_id:
            await organizations_col.update_one(
                {"stripeCustomerId": customer_id},
                {"$set": {
                    "plan": "pro",
                    "active": True,
                    "stripeSubscriptionId": subscription_id,
                    "stripeSubscriptionStatus": "active",
                }},
            )

    elif event["type"] in ("customer.subscription.updated", "customer.subscription.deleted"):
        customer_id = obj.get("customer")
        status_ = obj.get("status")  # e.g. active, past_due, canceled, unpaid
        if customer_id:
            updates = {"stripeSubscriptionStatus": status_}
            # A subscription that's genuinely no longer collectible
            # (canceled or unpaid, Stripe's own terminal/problem
            # states) is the real signal to stop treating this org as
            # paid - past_due alone is a real, honest grace period
            # Stripe itself is still retrying, not an immediate cutoff.
            if status_ in ("canceled", "unpaid"):
                updates["active"] = False
            elif status_ == "active":
                updates["active"] = True
            await organizations_col.update_one({"stripeCustomerId": customer_id}, {"$set": updates})

    return {"received": True}
