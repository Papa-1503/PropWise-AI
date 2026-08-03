"""
Email sending via plain SMTP — works with any provider (Gmail, SendGrid's
SMTP relay, Mailgun, your own mail server, etc.) by just changing env vars,
rather than locking the codebase to one vendor's API.

Required environment variables (see .env.example):
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, FROM_EMAIL

If these aren't set, send_email() raises a clear error rather than
silently pretending to send — callers (the AI action executors) catch
this and report it honestly instead of marking an action "completed"
when nothing actually went out.
"""
import os
import asyncio
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


class EmailNotConfigured(Exception):
    pass


class EmailSendError(Exception):
    pass


def _get_config():
    host = os.getenv("SMTP_HOST")
    port = os.getenv("SMTP_PORT")
    user = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASSWORD")
    from_email = os.getenv("FROM_EMAIL", user)

    if not all([host, port, user, password]):
        raise EmailNotConfigured(
            "SMTP_HOST, SMTP_PORT, SMTP_USER, and SMTP_PASSWORD must all be set in the "
            "environment for email sending to work. See backend/.env.example."
        )
    return host, int(port), user, password, from_email


def send_email(to: str, subject: str, body_text: str, body_html: str | None = None) -> None:
    """Sends a single email. Raises EmailNotConfigured or EmailSendError on failure —
    callers must handle these rather than assuming success."""
    host, port, user, password, from_email = _get_config()

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = to
    msg.attach(MIMEText(body_text, "plain"))
    if body_html:
        msg.attach(MIMEText(body_html, "html"))

    try:
        with smtplib.SMTP(host, port, timeout=10) as server:
            server.starttls()
            server.login(user, password)
            server.sendmail(from_email, [to], msg.as_string())
    except Exception as exc:
        raise EmailSendError(f"Failed to send email to {to}: {exc}") from exc


def send_bulk(recipients: list[dict]) -> dict:
    """
    recipients: [{"to": str, "subject": str, "body_text": str, "body_html": str|None}, ...]
    Returns {"sent": [...], "failed": [{"to": ..., "error": ...}, ...]} — never raises,
    so a batch send reports partial success honestly instead of all-or-nothing.

    NOTE: this function is BLOCKING (smtplib has no async API). Callers in
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
    """Async-safe wrapper — runs the blocking SMTP call in a thread pool
    so it doesn't stall the FastAPI event loop."""
    await asyncio.to_thread(send_email, to, subject, body_text, body_html)


async def send_bulk_async(recipients: list[dict]) -> dict:
    """Async-safe wrapper for send_bulk() — use this from FastAPI routes."""
    return await asyncio.to_thread(send_bulk, recipients)
