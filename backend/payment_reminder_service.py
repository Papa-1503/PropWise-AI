"""
Real, multi-channel payment reminder sending — in-app + push already
existed (notifications_service), but SMS and email were genuinely
missing from this specific flow (Twilio/email infrastructure exists
elsewhere in this app, just was never wired into payment reminders).

Shared by both the automated check (_do_payment_reminder_check in
routers/admin.py) and the manual "send reminder now" staff action
(routers/payments.py's /send-reminder), so both paths send the exact
same real message through the exact same real channels, and share the
exact same cooldown — a resident can never be spammed regardless of
which path triggered a send, and staff clicking "send now" can never
bypass the same spam-prevention the automated schedule respects.
"""
from datetime import datetime, timezone, timedelta

from db import leases_col
import notifications_service
import sms_service
from sms_service import SmsNotConfigured, SmsSendError
import email_service
from email_service import EmailNotConfigured, EmailSendError

REMINDER_COOLDOWN_HOURS = 48


def reminder_eligible(charge: dict, now: datetime | None = None) -> bool:
    """A charge is eligible for a reminder if it's never had one, or its
    last one was sent more than REMINDER_COOLDOWN_HOURS ago — real,
    repeatable reminders while a charge stays unpaid, not the previous
    single one-and-done notice (the old reminderSent boolean is no
    longer used for this — see lastReminderSentAt instead)."""
    now = now or datetime.now(timezone.utc)
    last_sent = charge.get("lastReminderSentAt")
    if not last_sent:
        return True
    if isinstance(last_sent, datetime) and last_sent.tzinfo is None:
        last_sent = last_sent.replace(tzinfo=timezone.utc)
    return (now - last_sent) >= timedelta(hours=REMINDER_COOLDOWN_HOURS)


async def send_payment_reminder(charge: dict) -> dict:
    """Sends a real reminder through every channel available for this
    resident — in-app/push (always, if this charge resolves to a real
    unit resident), plus real SMS and email when the resident's lease
    has a phone/email on file AND Twilio/the email provider are
    actually configured. Honest per-channel reporting, not a single
    pass/fail — a resident with no phone on file still gets the
    in-app + email reminder, and staff can see exactly which channels
    a specific reminder actually went out on, same honesty pattern as
    vendor_sla_service.py's dispatch_with_sla."""
    property_id = charge.get("propertyId")
    unit_id = charge.get("unitId")
    amount_owed = charge.get("amountDue", 0) - charge.get("amountPaid", 0)
    due_date = charge.get("dueDate")
    due_str = due_date.strftime("%B %d, %Y") if isinstance(due_date, datetime) else "your due date"
    description = charge.get("description", "your charge")

    result = {
        "inApp": False,
        "sms": {"attempted": False, "sent": False, "note": ""},
        "email": {"attempted": False, "sent": False, "note": ""},
    }

    if property_id and unit_id:
        await notifications_service.notify_unit_resident(
            property_id, unit_id,
            type="general",
            title="Upcoming payment due",
            body=f"${amount_owed:.2f} due {due_str} for {description}",
            link="/payments",
        )
        result["inApp"] = True

    lease = await leases_col.find_one({"propertyId": property_id, "unitId": unit_id}) if property_id and unit_id else None

    if lease and lease.get("residentPhone"):
        result["sms"]["attempted"] = True
        try:
            sms_body = (
                f"PropWise AI: ${amount_owed:.2f} is due for {description} "
                f"(due {due_str}). Pay in the app or contact the office."
            )
            await sms_service.send_sms_async(lease["residentPhone"], sms_body)
            result["sms"]["sent"] = True
        except (SmsNotConfigured, SmsSendError) as exc:
            result["sms"]["note"] = str(exc)
    else:
        result["sms"]["note"] = "No phone number on file for this resident."

    if lease and lease.get("residentEmail"):
        result["email"]["attempted"] = True
        try:
            await email_service.send_email_async(
                to=lease["residentEmail"],
                subject="Upcoming payment due",
                body_text=(
                    f"${amount_owed:.2f} is due {due_str} for {description}. "
                    f"Please log in to PropWise AI to pay, or contact the property "
                    f"office with any questions."
                ),
            )
            result["email"]["sent"] = True
        except (EmailNotConfigured, EmailSendError) as exc:
            result["email"]["note"] = str(exc)
    else:
        result["email"]["note"] = "No email on file for this resident."

    return result
