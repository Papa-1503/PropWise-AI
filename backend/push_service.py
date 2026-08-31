"""
Push notification sending via the Web Push protocol (pywebpush), for
Priority 8 — notifications that reach a user even when PropWise AI
isn't open, unlike the existing in-app notification bell.

Required environment variables (see .env.example):
    VAPID_PRIVATE_KEY_PEM  — the private key's PEM text, generated once
    VAPID_CLAIMS_EMAIL     — a mailto: contact required by the Web Push
                              spec, identifying who's running this push
                              service to the browser vendors' push
                              relays (Google/Mozilla/etc.)

The matching PUBLIC key is not a secret — it's hardcoded directly in
the frontend (see PushSetup.jsx), since the browser needs it to create
a subscription in the first place, before the backend is ever involved.

Same honest philosophy as email_service.py: if not configured, or if
a real send fails, this raises a clear exception rather than silently
pretending to have sent something. A single subscription being expired
or invalid (the browser un-subscribed, e.g. after uninstalling the
PWA) is reported as PushSubscriptionExpired specifically, since callers
should react to that by deleting the stale subscription, not by
treating it as a general failure worth retrying.
"""
import os
import json
import asyncio
from pywebpush import webpush, WebPushException
from py_vapid import Vapid02


class PushNotConfigured(Exception):
    pass


class PushSendError(Exception):
    pass


class PushSubscriptionExpired(Exception):
    """The subscription itself is dead (browser returned 404/410) —
    the caller should delete it from push_subscriptions_col, not retry."""
    pass


def _get_config():
    private_key_pem = os.getenv("VAPID_PRIVATE_KEY_PEM")
    claims_email = os.getenv("VAPID_CLAIMS_EMAIL")
    if not all([private_key_pem, claims_email]):
        raise PushNotConfigured(
            "VAPID_PRIVATE_KEY_PEM and VAPID_CLAIMS_EMAIL must both be set in the "
            "environment for push notifications to work. See backend/.env.example."
        )
    return private_key_pem, claims_email


def send_push(subscription_info: dict, title: str, body: str, link: str | None = None) -> None:
    """subscription_info is exactly what the browser's PushSubscription.toJSON()
    produces — {endpoint, keys: {p256dh, auth}} — stored as-is in
    push_subscriptions_col when the frontend registers."""
    private_key_pem, claims_email = _get_config()
    # pywebpush's vapid_private_key parameter expects a Vapid instance or a
    # FILE PATH string, not raw PEM text directly (confirmed from its own
    # docstring/example — passing PEM text directly would fail). Loading
    # into a Vapid02 instance in memory avoids writing the private key to
    # a temp file on every send.
    vapid = Vapid02.from_pem(private_key_pem.encode())
    payload = json.dumps({"title": title, "body": body, "link": link or "/"})
    try:
        webpush(
            subscription_info=subscription_info,
            data=payload,
            vapid_private_key=vapid,
            vapid_claims={"sub": f"mailto:{claims_email}"},
        )
    except WebPushException as exc:
        status = getattr(exc.response, "status_code", None)
        if status in (404, 410):
            raise PushSubscriptionExpired(str(exc)) from exc
        raise PushSendError(str(exc)) from exc


async def send_push_async(subscription_info: dict, title: str, body: str, link: str | None = None) -> None:
    """Async-safe wrapper — runs the blocking HTTP call in a thread pool
    so it doesn't stall the FastAPI event loop, matching send_email_async."""
    await asyncio.to_thread(send_push, subscription_info, title, body, link)
