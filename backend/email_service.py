"""
Email sending via Mailgun's HTTP API.

CHANGED from plain SMTP (Aug 24, 2026): Render's free tier blocks all
outbound traffic to SMTP ports 25, 465, and 587 (confirmed via Render's
own changelog, effective Sept 26, 2025) — SMTP simply cannot work here
without upgrading to a paid Render instance. Mailgun's API sends over
HTTPS (port 443), which isn't blocked, so this keeps email working on
the free tier. All function names/signatures are unchanged from the old
SMTP version — callers (workflow_actions.py, communications.py) needed
zero changes.

Required environment variables (see .env.example):
    MAILGUN_API_KEY, MAILGUN_DOMAIN, FROM_EMAIL

MAILGUN_DOMAIN can be Mailgun's own sandbox domain (works immediately,
but can only send to pre-authorized recipient addresses — add
recipients in the Mailgun dashboard under the sandbox domain's
"Authorized Recipients") or a real verified custom domain once DNS is
set up, which can send to anyone.

If these aren't set, send_email() raises a clear error rather than
silently pretending to send — callers catch this and report it
honestly instead of marking an action "completed" when nothing
actually went out.
"""
import os
import asyncio
import httpx


class EmailNotConfigured(Exception):
    pass


class EmailSendError(Exception):
    pass


def _get_config():
    api_key = os.getenv("MAILGUN_API_KEY")
    domain = os.getenv("MAILGUN_DOMAIN")
    from_email = os.getenv("FROM_EMAIL")

    if not all([api_key, domain, from_email]):
        raise EmailNotConfigured(
            "MAILGUN_API_KEY, MAILGUN_DOMAIN, and FROM_EMAIL must all be set in the "
            "environment for email sending to work. See backend/.env.example."
        )
    return api_key, domain, from_email


def send_email(to: str, subject: str, body_text: str, body_html: str | None = None) -> None:
    """Sends a single email via Mailgun's HTTP API. Raises EmailNotConfigured or
    EmailSendError on failure — callers must handle these rather than assuming success."""
    api_key, domain, from_email = _get_config()

    data = {
        "from": from_email,
        "to": to,
        "subject": subject,
        "text": body_text,
    }
    if body_html:
        data["html"] = body_html

    try:
        with httpx.Client(timeout=10) as client:
            resp = client.post(
                f"https://api.mailgun.net/v3/{domain}/messages",
                auth=("api", api_key),
                data=data,
            )
        if resp.status_code >= 400:
            raise EmailSendError(f"Failed to send email to {to}: Mailgun returned {resp.status_code}: {resp.text}")
    except httpx.HTTPError as exc:
        raise EmailSendError(f"Failed to send email to {to}: {exc}") from exc


def send_bulk(recipients: list[dict]) -> dict:
    """
    recipients: [{"to": str, "subject": str, "body_text": str, "body_html": str|None}, ...]
    Returns {"sent": [...], "failed": [{"to": ..., "error": ...}, ...]} — never raises,
    so a batch send reports partial success honestly instead of all-or-nothing.

    NOTE: this function is BLOCKING (uses a sync httpx.Client). Callers in
    FastAPI async routes should use send_bulk_async() below instead of
    calling this directly, or every other request will stall while a
    bulk send is in progress.
    """
    sent, failed = [], []
    for r in recipients:
        try:
            send_email(r["to"], r["subject"], r["body_text"], r.get("body_html"))
            sent.append(r["to"])
        except (EmailNotConfigured, EmailSendError) as exc:
            failed.append({"to": r["to"], "error": str(exc)})
    return {"sent": sent, "failed": failed}


async def send_email_async(to: str, subject: str, body_text: str, body_html: str | None = None) -> None:
    """Async-safe wrapper — runs the blocking HTTP call in a thread pool
    so it doesn't stall the FastAPI event loop."""
    await asyncio.to_thread(send_email, to, subject, body_text, body_html)


async def send_bulk_async(recipients: list[dict]) -> dict:
    """Async-safe wrapper for send_bulk() — use this from FastAPI routes."""
    return await asyncio.to_thread(send_bulk, recipients)
