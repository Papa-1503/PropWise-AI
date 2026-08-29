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
    TWILIO_FROM_NUMBER   — the Twilio number sends originate from, E.164
                            format (e.g. +15551234567)
"""
import os
import asyncio

from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException


class SmsNotConfigured(Exception):
    pass


class SmsSendError(Exception):
    pass


def _get_client():
    sid = os.getenv("TWILIO_ACCOUNT_SID")
    token = os.getenv("TWILIO_AUTH_TOKEN")
    from_number = os.getenv("TWILIO_FROM_NUMBER")
    if not all([sid, token, from_number]):
        raise SmsNotConfigured(
            "TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, and TWILIO_FROM_NUMBER must all be "
            "set in the environment for SMS sending to work. See backend/.env.example."
        )
    return Client(sid, token), from_number


def send_sms(to: str, body: str) -> str:
    """Returns the real Twilio message SID on success — callers can use
    it to look up delivery status later if needed. Raises SmsSendError
    with Twilio's own error message on a real rejection (bad number,
    unverified trial-account recipient, etc.) rather than swallowing it."""
    client, from_number = _get_client()
    try:
        message = client.messages.create(to=to, from_=from_number, body=body)
        return message.sid
    except TwilioRestException as exc:
        raise SmsSendError(f"Twilio error {exc.code}: {exc.msg}") from exc


async def send_sms_async(to: str, body: str) -> str:
    """Async-safe wrapper — runs the blocking Twilio SDK call in a thread
    pool so it doesn't stall the FastAPI event loop, matching
    send_email_async/send_push_async."""
    return await asyncio.to_thread(send_sms, to, body)
