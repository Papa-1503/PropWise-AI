"""
Stripe Billing — the SaaS subscription layer for this app itself
(an organization paying PropWise AI to use the product), genuinely
distinct from stripe_service.py (a RESIDENT paying THEIR landlord
rent via ACH). Same Stripe account can power both — they're
different real products (Billing/Subscriptions vs. Payments/ACH) — but
this uses its own real Stripe Customer per ORGANIZATION (keyed by
rentflow_org_id metadata, not rentflow_user_id), its own real webhook
endpoint/secret, and Stripe's Checkout + Customer Portal products
rather than a hand-rolled SetupIntent/PaymentIntent flow, since a
subscription's real lifecycle (trial, active, past_due, canceled) is
exactly what Stripe Billing is built to manage - reimplementing that
state machine by hand here would be real, unnecessary risk.

Required environment variables:
    STRIPE_SECRET_KEY          — same key stripe_service.py uses, one
                                  real Stripe account for both products
    STRIPE_PRICE_ID             — the real Stripe Price ID for this
                                  app's paid plan (created once, by
                                  hand, in the Stripe dashboard under
                                  Product catalog - this app has
                                  exactly one real paid tier for now,
                                  not a multi-tier price list; see
                                  routers/billing.py's own module
                                  docstring for why multi-tier is real,
                                  separate follow-on work)
    STRIPE_BILLING_WEBHOOK_SECRET — a SEPARATE signing secret from
                                  STRIPE_WEBHOOK_SECRET (rent ACH's own
                                  webhook) - configured as a second,
                                  distinct webhook endpoint in the
                                  Stripe dashboard pointed at
                                  /api/billing/webhook, listening for
                                  subscription lifecycle events
                                  (checkout.session.completed,
                                  customer.subscription.updated,
                                  customer.subscription.deleted) rather
                                  than the payment_intent.* events the
                                  existing rent-payment webhook
                                  handles. Two separate secrets so a
                                  compromised or misconfigured one
                                  can never be replayed against the
                                  other endpoint.
"""
import os
import asyncio

import stripe


class StripeNotConfigured(Exception):
    pass


class StripePayError(Exception):
    pass


def _get_client_configured() -> None:
    key = os.getenv("STRIPE_SECRET_KEY")
    if not key:
        raise StripeNotConfigured(
            "STRIPE_SECRET_KEY must be set in the environment for billing to work. "
            "See backend/.env.example. Sign up at https://dashboard.stripe.com."
        )
    stripe.api_key = key


def get_or_create_org_customer(org_id: str, email: str, org_name: str) -> str:
    """Returns a real Stripe Customer ID for this ORGANIZATION (not a
    resident/user) - reuses an existing one if this exact org_id was
    already used as the rentflow_org_id metadata key on a prior call,
    the same dedup-via-metadata pattern stripe_service.py's own
    get_or_create_customer already established for per-user customers.
    Callers should still persist the returned ID on the organization
    document (stripeCustomerId) rather than calling this every time;
    this lookup is a safety net, not the primary mechanism."""
    _get_client_configured()
    existing = stripe.Customer.list(email=email, limit=10)
    for c in existing.data:
        # BUG FIX (found live via Sentry, real production error -
        # /api/billing/checkout raised AttributeError:
        # "'get' is a dict method, but a StripeObject is not a dict"):
        # c.metadata is itself a StripeObject, not a plain dict, same
        # real issue already fixed in routers/billing.py's webhook
        # handler. StripeObject DOES support attribute access
        # reliably (confirmed by session.url/session.id working fine
        # elsewhere in this same file) - getattr with a default is the
        # correct, safe fix here, matching that same proven pattern,
        # rather than converting the whole object with .to_dict() for
        # a single field.
        if getattr(c.metadata, "rentflow_org_id", None) == org_id:
            return c.id
    customer = stripe.Customer.create(
        email=email,
        name=org_name,
        metadata={"rentflow_org_id": org_id},
    )
    return customer.id


def create_checkout_session(customer_id: str, price_id: str, success_url: str, cancel_url: str) -> dict:
    """Real Stripe Checkout Session in subscription mode - the actual
    upgrade flow. This backend never collects or sees a card number;
    Checkout is Stripe's own hosted page, the same real security
    boundary already established for bank-account linking in
    stripe_service.py's SetupIntent flow (this backend only ever
    handles tokenized IDs and URLs, never raw payment details)."""
    _get_client_configured()
    try:
        session = stripe.checkout.Session.create(
            customer=customer_id,
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=success_url,
            cancel_url=cancel_url,
        )
        return {"checkoutUrl": session.url, "sessionId": session.id}
    except stripe.error.StripeError as exc:
        raise StripePayError(f"Stripe error: {exc.user_message or str(exc)}") from exc


def create_billing_portal_session(customer_id: str, return_url: str) -> dict:
    """Real Stripe Customer Portal session - the actual self-serve
    'manage my subscription' flow (update payment method, view real
    past invoices, cancel). Genuinely self-serve: no staff action on
    this app's side is needed for an org owner to cancel or update
    their own billing, matching how a real SaaS product's billing
    self-service is expected to work."""
    _get_client_configured()
    try:
        session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=return_url,
        )
        return {"portalUrl": session.url}
    except stripe.error.StripeError as exc:
        raise StripePayError(f"Stripe error: {exc.user_message or str(exc)}") from exc


def construct_billing_webhook_event(payload: bytes, sig_header: str) -> "stripe.Event":
    """Verifies a webhook request actually came from Stripe before
    trusting its contents - same real security boundary as
    stripe_service.py's construct_webhook_event, deliberately using a
    SEPARATE signing secret (STRIPE_BILLING_WEBHOOK_SECRET) - see this
    module's own docstring for why the two webhook streams (rent ACH
    vs. subscription lifecycle) are kept genuinely independent rather
    than sharing one secret."""
    secret = os.getenv("STRIPE_BILLING_WEBHOOK_SECRET")
    if not secret:
        raise StripeNotConfigured("STRIPE_BILLING_WEBHOOK_SECRET must be set to verify Stripe billing webhooks.")
    try:
        return stripe.Webhook.construct_event(payload, sig_header, secret)
    except (ValueError, stripe.error.SignatureVerificationError) as exc:
        raise StripePayError(f"Invalid Stripe webhook signature: {exc}") from exc


async def get_or_create_org_customer_async(org_id: str, email: str, org_name: str) -> str:
    return await asyncio.to_thread(get_or_create_org_customer, org_id, email, org_name)


async def create_checkout_session_async(customer_id: str, price_id: str, success_url: str, cancel_url: str) -> dict:
    return await asyncio.to_thread(create_checkout_session, customer_id, price_id, success_url, cancel_url)


async def create_billing_portal_session_async(customer_id: str, return_url: str) -> dict:
    return await asyncio.to_thread(create_billing_portal_session, customer_id, return_url)
