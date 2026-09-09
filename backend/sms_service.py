"""
SMS sending via Twilio — Priority 12, Step 3.

Same architectural template as email_service.py/push_service.py: a
sync function plus an async wrapper, and honest exceptions rather than
a silent no-op — SmsNotConfigured when the env vars aren't set,
SmsSendError when Twilio's API rejects the send for a real reason
(invalid number, unverified trial number, insufficient balance, etc.).

Required environment variables:
    TWILIO_ACCOUNT_SID
    TWILIO_AUTH_TOKEN
    TWILIO_FROM_NUMBER   — the shared, default Twilio number sends
                            originate from when an organization has
                            not configured its own dedicated number
                            (see get_org_sms_number below), E.164
                            format (e.g. +15551234567)

MULTI-TENANCY: real, structural limitation partially closed here. This
app previously had exactly ONE shared Twilio number for every
organization's inbound and outbound SMS combined - see
routers/sms_inbound.py's own module docstring for the full original
reasoning. Organizations can now optionally configure their own
dedicated Twilio number (organizations_col.smsNumber, set via
routers/organizations.py) - when configured, outbound sends on that
org's behalf use its own number (so residents recognize a consistent
sender), and inbound texts to that number are correctly scoped to
just that org. Organizations that haven't configured one still share
the single default TWILIO_FROM_NUMBER, with the same real, honestly-
documented cross-org ambiguity on the inbound side that always existed
for the shared number specifically - not a regression, just not yet
eliminated for orgs that opt not to set up their own number.
"""
import os
import asyncio

from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

from db import organizations_col


class SmsNotConfigured(Exception):
    pass


class SmsSendError(Exception):
    pass


def _get_client():
    sid = os.getenv("TWILIO_ACCOUNT_SID")
    token = os.getenv("TWILIO_AUTH_TOKEN")
    default_from_number = os.getenv("TWILIO_FROM_NUMBER")
    if not all([sid, token, default_from_number]):
        raise SmsNotConfigured(
            "TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, and TWILIO_FROM_NUMBER must all be "
            "set in the environment for SMS sending to work. See backend/.env.example."
        )
    return Client(sid, token), default_from_number


async def get_org_sms_number(org_id: str | None) -> str | None:
    """Returns the real, dedicated Twilio number an organization has
    configured for its own SMS traffic, or None if it hasn't set one
    up (callers should fall back to the shared TWILIO_FROM_NUMBER in
    that case)."""
    if not org_id:
        return None
    from bson import ObjectId
    query_id = ObjectId(org_id) if ObjectId.is_valid(org_id) else org_id
    org = await organizations_col.find_one({"_id": query_id}, {"smsNumber": 1})
    return org.get("smsNumber") if org else None


def send_sms(to: str, body: str, from_number: str | None = None) -> str:
    """Returns the real Twilio message SID on success — callers can use
    it to look up delivery status later if needed. Raises SmsSendError
    with Twilio's own error message on a real rejection (bad number,
    unverified trial-account recipient, etc.) rather than swallowing it.

    from_number, when given, overrides the shared default number - use
    get_org_sms_number to resolve an organization's own dedicated
    number first, where one is available."""
    client, default_from_number = _get_client()
    try:
        message = client.messages.create(to=to, from_=from_number or default_from_number, body=body)
        return message.sid
    except TwilioRestException as exc:
        raise SmsSendError(f"Twilio error {exc.code}: {exc.msg}") from exc


async def send_sms_async(to: str, body: str, from_number: str | None = None) -> str:
    """Async-safe wrapper — runs the blocking Twilio SDK call in a thread
    pool so it doesn't stall the FastAPI event loop, matching
    send_email_async/send_push_async."""
    return await asyncio.to_thread(send_sms, to, body, from_number)
