"""
Organization-level SaaS billing — trial status, upgrade checkout, and
self-serve subscription management. Distinct from routers/payments.py
(a resident paying rent) and routers/reconciliation.py (bank
reconciliation) - this is the OTHER real financial flow this app
needs: this app's own customer (an organization) paying to keep using
PropWise AI.

GET  /api/billing/status    -> real current plan/trial/tier state for
                                the caller's own org
GET  /api/billing/tiers     -> the 3 real tier definitions (price,
                                unit guidance) plus this org's own
                                current real unit count, so the
                                frontend can render tier cards with an
                                honest "recommended for you" badge
POST /api/billing/checkout  -> (org owner) creates a real Stripe
                                Checkout Session for a CHOSEN tier,
                                returns the URL to redirect to
POST /api/billing/portal    -> (org owner) creates a real Stripe
                                Customer Portal session for self-serve
                                management (payment method, invoices,
                                cancel)
POST /api/billing/webhook   -> PUBLIC, Stripe-signed - real
                                subscription lifecycle events land
                                here and update the organization's
                                real plan/tier/active state

REAL, MULTI-TIER PRICING (added Sept 2026, replacing the earlier
single flat-rate plan): grounded in a real market comparison against
Buildium (flat $58-75/mo, limited AI) and AppFolio ($280-298/mo
minimum, AI gated behind premium tiers) - PropWise AI's own AI-
everywhere feature set sits closer to AppFolio's Plus/Max tier, priced
closer to Buildium's entry point. Three tiers, informally guided by
real portfolio size (not hard-enforced - see TIERS below), since a
5-unit landlord and a 300-unit management company get very different
value and drive very different real usage-based costs (see the unit
economics model built alongside this pricing decision).

Tier selection is tracked TWO ways for real robustness: (1) passed as
real Stripe metadata at Checkout time, read back immediately on
checkout.session.completed; (2) re-derived from the subscription's
actual current Price ID on every customer.subscription.updated event,
which self-heals if a customer changes tiers through the Stripe
Customer Portal rather than a fresh checkout - the org's stored
billingTier can never silently drift from what Stripe actually has
them subscribed to.

Requires billing_service.py's own environment variables
(STRIPE_SECRET_KEY, STRIPE_BILLING_WEBHOOK_SECRET) plus one Price ID
per tier (STRIPE_PRICE_ID_STARTER, STRIPE_PRICE_ID_GROWTH,
STRIPE_PRICE_ID_PRO) - see that module's docstring. Every endpoint
here fails with an honest 501/503, never a silent no-op, if billing
isn't configured.
"""
import os
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel, field_validator
from bson import ObjectId

from db import organizations_col, properties_col
from auth import get_current_user
import billing_service
from billing_service import StripeNotConfigured, StripePayError

router = APIRouter(prefix="/api/billing", tags=["billing"])

# Real tier definitions - unitGuidance is informational only (shown to
# staff so they can pick sensibly), never hard-enforced. Enforcing a
# real unit cap that blocks usage past it is genuine, separate future
# work - deliberately not built here, since getting the enforcement
# UX right (a grace period? a hard block? an automatic upgrade
# prompt?) is a real product decision this pass doesn't make.
TIERS = {
    "starter": {"name": "Starter", "price": 79, "unitGuidance": "Best for up to ~25 units", "envVar": "STRIPE_PRICE_ID_STARTER"},
    "growth": {"name": "Growth", "price": 249, "unitGuidance": "Best for ~25-100 units", "envVar": "STRIPE_PRICE_ID_GROWTH"},
    "pro": {"name": "Pro", "price": 599, "unitGuidance": "Best for 100+ units", "envVar": "STRIPE_PRICE_ID_PRO"},
}


class CheckoutRequest(BaseModel):
    tier: str
    successUrl: str
    cancelUrl: str

    @field_validator("tier")
    @classmethod
    def validate_tier(cls, v):
        if v not in TIERS:
            raise ValueError(f"tier must be one of {', '.join(TIERS.keys())}")
        return v


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
        "billingTier": org.get("billingTier"),
    }


async def _real_unit_count(org_id: str) -> int:
    """The org's real, current total unit count across every property
    - summed live from properties_col, never a separately-stored
    counter that could go stale. Used only to give staff an honest
    tier recommendation; never used to block or gate anything."""
    properties = await properties_col.find({"orgId": org_id}, {"units": 1}).to_list(length=1000)
    return sum(len(p.get("units", [])) for p in properties)


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


@router.get("/tiers")
async def get_billing_tiers(user: dict = Depends(get_current_user)):
    """The real 3 tiers plus this org's own real, live unit count, so
    the frontend can show an honest 'recommended for you' badge -
    never a hard gate, just a genuinely useful default."""
    org_id = user.get("orgId")
    unit_count = await _real_unit_count(org_id) if org_id else 0

    if unit_count <= 25:
        recommended = "starter"
    elif unit_count <= 100:
        recommended = "growth"
    else:
        recommended = "pro"

    tiers_out = [
        {"id": tier_id, "name": t["name"], "price": t["price"], "unitGuidance": t["unitGuidance"]}
        for tier_id, t in TIERS.items()
    ]
    return {"tiers": tiers_out, "yourUnitCount": unit_count, "recommendedTier": recommended}


@router.post("/checkout")
async def create_checkout(payload: CheckoutRequest, user: dict = Depends(_require_org_owner)):
    price_id = os.getenv(TIERS[payload.tier]["envVar"])
    if not price_id:
        raise HTTPException(status_code=501, detail=f"Billing isn't fully configured yet — {TIERS[payload.tier]['envVar']} is not set.")

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
            customer_id, price_id, payload.successUrl, payload.cancelUrl,
            metadata={"tier": payload.tier, "rentflow_org_id": org_id},
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


def _tier_from_price_id(price_id: str | None) -> str | None:
    """Robustly re-derives which real tier a Stripe Price ID
    corresponds to, by matching against this app's own configured
    env vars - the real mechanism that keeps billingTier correct even
    after an in-portal plan change, not just at initial checkout."""
    if not price_id:
        return None
    for tier_id, t in TIERS.items():
        if os.getenv(t["envVar"]) == price_id:
            return tier_id
    return None


@router.post("/webhook")
async def billing_webhook(request: Request):
    """Real, security-boundary-verified endpoint - see
    billing_service.py's construct_billing_webhook_event. Public (no
    user session possible - Stripe calls this directly), so signature
    verification is the only thing standing between this endpoint and
    a forged 'subscription active' event.

    checkout.session.completed is when a trial genuinely converts to
    paid - the real moment plan flips to 'pro', and billingTier is set
    from the real Checkout metadata. subscription.updated/deleted keep
    the org's real status AND tier in sync with whatever actually
    happens afterward (a failed renewal charge, a real cancellation,
    or a real in-portal plan change) - an org is never silently left
    marked 'pro' after its subscription has actually lapsed, or on the
    wrong tier after switching plans."""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    try:
        event = billing_service.construct_billing_webhook_event(payload, sig_header)
    except (StripeNotConfigured, StripePayError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # BUG FIX (found by actually running a real, validly-signed test
    # webhook through this handler, not assumed correct): stripe's
    # Event.data.object is a StripeObject, not a plain dict - it
    # supports [] access but NOT .get(), which raises AttributeError
    # ("'get' is a dict method, but a StripeObject is not a dict").
    # Every .get() call below would have raised the moment a REAL
    # Stripe webhook fired in production. .to_dict() converts it to a
    # real plain dict first, after which every .get() call below
    # behaves exactly as written.
    obj = event["data"]["object"].to_dict()

    if event["type"] == "checkout.session.completed":
        customer_id = obj.get("customer")
        subscription_id = obj.get("subscription")
        tier = obj.get("metadata", {}).get("tier")
        if customer_id:
            updates = {
                "plan": "pro",
                "active": True,
                "stripeSubscriptionId": subscription_id,
                "stripeSubscriptionStatus": "active",
            }
            if tier in TIERS:
                updates["billingTier"] = tier
            await organizations_col.update_one(
                {"stripeCustomerId": customer_id}, {"$set": updates},
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

            # Real, self-healing tier re-derivation - covers a plan
            # change made through the Stripe Customer Portal, which
            # never goes through /checkout's metadata path at all.
            items = obj.get("items", {}).get("data", [])
            if items:
                current_price_id = items[0].get("price", {}).get("id")
                derived_tier = _tier_from_price_id(current_price_id)
                if derived_tier:
                    updates["billingTier"] = derived_tier

            await organizations_col.update_one({"stripeCustomerId": customer_id}, {"$set": updates})

    return {"received": True}
