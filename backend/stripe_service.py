"""
Stripe ACH Direct Debit — online rent collection / autopay.

Same architectural template as sms_service.py/email_service.py: sync
functions plus async wrappers, honest exceptions rather than a silent
no-op. StripeNotConfigured when the env var isn't set, StripePayError
when Stripe's API rejects a call for a real reason.

Required environment variable:
    STRIPE_SECRET_KEY   — starts with sk_test_... or sk_live_...

Real ACH-specific design notes, not a generic Stripe wrapper:

- ACH is fundamentally different from a card charge: it's asynchronous.
  A card payment succeeds or fails in the same request; an ACH debit
  takes 4-5 business days to actually clear, and can still bounce after
  looking successful (insufficient funds, closed account, an R01/R02
  return code days later). This means the ledger CANNOT be marked paid
  the moment a PaymentIntent is created — only when Stripe's own
  webhook confirms payment_intent.succeeded, and it needs to be able to
  reverse a payment on payment_intent.payment_failed even after the
  fact. See routers/payments.py's webhook handler.

- Uses payment_method_types=["us_bank_account"] specifically, not the
  default "automatic" type list, so a resident can't accidentally end
  up on a card charge (different fee structure, different failure
  mode) when the whole point of this feature is ACH.

- Bank account linking/verification (Stripe Financial Connections, or
  older micro-deposit verification) happens through Stripe's own
  client-side flow (Stripe.js SetupIntent confirmation) — this backend
  never sees, handles, or stores a raw account/routing number, only
  the resulting tokenized paymentMethodId. That's both a real security
  boundary (this app doesn't become a target for bank credential theft)
  and how Stripe's ACH product is actually meant to be integrated.
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
            "STRIPE_SECRET_KEY must be set in the environment for online payments to "
            "work. See backend/.env.example. Sign up at https://dashboard.stripe.com "
            "and enable ACH Direct Debit under Settings > Payment methods."
        )
    stripe.api_key = key


def get_or_create_customer(user_id: str, email: str, name: str) -> str:
    """Returns a Stripe Customer ID, reusing an existing one if this
    exact user_id was already used as Stripe's idempotency/metadata key
    on a prior call — avoids creating a duplicate Stripe customer every
    time a resident revisits the autopay setup page. Callers should
    still persist the returned ID on the user document (stripeCustomerId)
    rather than calling this on every request; this dedup is a safety
    net, not the primary mechanism."""
    _get_client_configured()
    existing = stripe.Customer.list(email=email, limit=1)
    for c in existing.data:
        if c.metadata.get("rentflow_user_id") == user_id:
            return c.id
    customer = stripe.Customer.create(
        email=email,
        name=name,
        metadata={"rentflow_user_id": user_id},
    )
    return customer.id


def create_setup_intent(customer_id: str) -> dict:
    """Starts the bank-account-linking flow. Returns the client_secret
    the frontend needs to complete verification via Stripe.js — this
    backend's role ends here; the actual account linking/micro-deposit
    verification happens entirely in the browser against Stripe's API
    directly, never routed through this server."""
    _get_client_configured()
    try:
        intent = stripe.SetupIntent.create(
            customer=customer_id,
            payment_method_types=["us_bank_account"],
        )
        return {"clientSecret": intent.client_secret, "setupIntentId": intent.id}
    except stripe.error.StripeError as exc:
        raise StripePayError(f"Stripe error: {exc.user_message or str(exc)}") from exc


def create_ach_payment_intent(customer_id: str, payment_method_id: str, amount_cents: int, description: str) -> dict:
    """Charges a previously-linked bank account. Returns the raw
    PaymentIntent id and status - status will be 'processing', not
    'succeeded', immediately after this call for ACH specifically
    (unlike a card charge); the real outcome arrives later via webhook.
    Callers must not mark a charge as paid based on this return value
    alone."""
    _get_client_configured()
    try:
        intent = stripe.PaymentIntent.create(
            customer=customer_id,
            payment_method=payment_method_id,
            payment_method_types=["us_bank_account"],
            amount=amount_cents,
            currency="usd",
            confirm=True,
            off_session=True,  # recurring/scheduled autopay charge, resident isn't present
            description=description,
        )
        return {"paymentIntentId": intent.id, "status": intent.status}
    except stripe.error.CardError as exc:
        # Despite the name, Stripe raises CardError for bank-account
        # failures too (insufficient funds, etc.) in some cases -
        # surfaced with the real decline reason rather than a generic
        # message.
        raise StripePayError(f"Payment failed: {exc.user_message or str(exc)}") from exc
    except stripe.error.StripeError as exc:
        raise StripePayError(f"Stripe error: {exc.user_message or str(exc)}") from exc


def construct_webhook_event(payload: bytes, sig_header: str) -> "stripe.Event":
    """Verifies a webhook request actually came from Stripe (not a
    forged request hitting a guessed URL) before trusting its contents
    — same security boundary as Twilio's request signature validation
    in routers/telephony.py, different mechanism (HMAC over the raw
    body + a timestamp, not a signed URL)."""
    secret = os.getenv("STRIPE_WEBHOOK_SECRET")
    if not secret:
        raise StripeNotConfigured("STRIPE_WEBHOOK_SECRET must be set to verify Stripe webhooks.")
    try:
        return stripe.Webhook.construct_event(payload, sig_header, secret)
    except (ValueError, stripe.error.SignatureVerificationError) as exc:
        raise StripePayError(f"Invalid Stripe webhook signature: {exc}") from exc


async def get_or_create_customer_async(user_id: str, email: str, name: str) -> str:
    return await asyncio.to_thread(get_or_create_customer, user_id, email, name)


async def create_setup_intent_async(customer_id: str) -> dict:
    return await asyncio.to_thread(create_setup_intent, customer_id)


async def create_ach_payment_intent_async(customer_id: str, payment_method_id: str, amount_cents: int, description: str) -> dict:
    return await asyncio.to_thread(create_ach_payment_intent, customer_id, payment_method_id, amount_cents, description)
