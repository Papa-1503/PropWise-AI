"""
One-off admin endpoints to trigger scheduled jobs without shell access
(not available on Render's free tier). Protected by a shared secret,
not staff auth, since these are meant to be called by an external
scheduler (e.g. cron-job.org, configured to send a POST with the key
in the JSON body) rather than from the app itself.

CHANGED Aug 25, 2026: these were originally GET requests with the key
in the URL — flagged independently by two external audits, verified as
a real (if lower-severity, since the key check itself was always
genuinely enforced) hardening gap: state-changing actions as GET
requests risk the key leaking via browser history, server access logs,
and proxy/CDN caching. Now POST, with the key in the request body. This
does mean these can no longer be triggered by just visiting a URL in a
browser tab — use ReqBin (or any HTTP client) with a POST + JSON body,
or reconfigure any external cron service accordingly.

/seed-demo             -> (existing) triggers demo simulation seed data
/run-maintenance-check  -> finds preventive maintenance schedules that are
                           due, creates a ticket for each, advances their
                           next due date. Safe to run repeatedly — only
                           acts on schedules that are actually due.
/seed-scale-test        -> generates 12 additional properties (~1,838
                           units) with leases, payment history, tickets,
                           a rotating tech pool, and owner accounts, to
                           test the data model at real portfolio scale.
                           Can take a while to run given the volume —
                           safe to re-run, skips existing properties.
/run-lease-renewal-check -> finds leases expiring within a window (default
                           60 days) that haven't been notified yet
                           (renewalStatus == "not_sent"), notifies both
                           the resident and the property's assigned tech,
                           then marks renewalStatus "sent" so the same
                           lease doesn't get renotified every run.
/run-payment-reminder-check -> finds charges due within a window (default
                           5 days) that aren't fully paid and haven't
                           been reminded yet, notifies the resident, then
                           marks reminderSent so the same charge doesn't
                           get renotified every run.
/run-late-fee-check     -> finds unpaid charges whose grace period has
                           passed, adds a late fee to amountDue (amount
                           and grace period configurable per property via
                           lateFeeAmount/lateFeeGraceDays fields, default
                           $50 / 5 days if a property hasn't set its own),
                           notifies the resident, marks lateFeeApplied so
                           it's only ever charged once per charge.
"""
import os
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException, Depends
from bson import ObjectId

from db import maintenance_schedules_col, tickets_col, users_col, leases_col, payments_col, properties_col, ai_actions_col, late_notices_col, scheduler_health_col, vendors_col
from models import AdminKeyPayload
from stripe_service import (
    StripeNotConfigured,
    StripePayError,
    create_ach_payment_intent_async,
)
import notifications_service
import vendor_sla_service
import renewal_risk_service
import payment_reminder_service
from auth import require_staff

DEFAULT_LATE_FEE_AMOUNT = 50.0
DEFAULT_LATE_FEE_GRACE_DAYS = 5

router = APIRouter(prefix="/api/admin", tags=["admin"])


def check_key(key: str):
    expected = os.getenv("SEED_SECRET")
    if not expected:
        raise HTTPException(status_code=500, detail="SEED_SECRET is not configured")
    if key != expected:
        raise HTTPException(status_code=403, detail="Invalid key")


@router.post("/seed-demo")
async def seed_demo(payload: AdminKeyPayload):
    check_key(payload.key)
    from scripts.seed_property_data import seed
    await seed()
    return {"status": "done", "message": "Simulation data seeded. Refresh the app to see it."}


@router.post("/seed-scale-test")
async def seed_scale_test(payload: AdminKeyPayload):
    check_key(payload.key)
    from scripts.seed_scale_test import seed
    await seed()
    return {"status": "done", "message": "Scale test data seeded — 12 new properties, ~1,838 units."}


@router.post("/run-maintenance-check")
async def run_maintenance_check(payload: AdminKeyPayload):
    check_key(payload.key)
    return await _do_maintenance_check()


async def _do_maintenance_check():
    """Split out from the HTTP handler above, same pattern as
    _do_late_fee_check/_do_escalation_check, so the real background
    scheduler (main.py) can call this directly without an admin key —
    the key exists to gate the external HTTP trigger, not to gate the
    check itself from running automatically."""
    now = datetime.now(timezone.utc)
    cursor = maintenance_schedules_col.find({"active": True, "nextDueDate": {"$lte": now}})
    due_schedules = await cursor.to_list(length=500)

    created = []
    for schedule in due_schedules:
        ticket = {
            "propertyId": schedule["propertyId"],
            "unitId": schedule.get("unitId"),
            "title": schedule["title"],
            "priority": "normal",
            "source": "preventive_maintenance",
            "sourceInspectionId": None,
            "room": None,
            "assignee": None,
            "category": schedule.get("category", "general"),
            "status": "open",
            "createdAt": now,
        }

        assigned_tech = await users_col.find_one({"role": "staff", "assignedProperties": schedule["propertyId"]})
        if assigned_tech:
            ticket["assignee"] = assigned_tech.get("email")

        result = await tickets_col.insert_one(ticket)
        created.append(str(result.inserted_id))

        if assigned_tech:
            await notifications_service.notify_user(
                str(assigned_tech["_id"]),
                type="general",
                title=f"Preventive maintenance due: {schedule['title']}",
                body=f"Property {schedule['propertyId']} — scheduled task now due",
                link=f"/maintenance/{str(result.inserted_id)}",
            )
        else:
            await notifications_service.notify_all_staff(
                type="general",
                title=f"Preventive maintenance due: {schedule['title']}",
                body=f"Property {schedule['propertyId']} — no tech assigned to this property yet",
                link=f"/maintenance/{str(result.inserted_id)}",
            )

        next_due = now + timedelta(days=schedule["intervalDays"])
        await maintenance_schedules_col.update_one(
            {"_id": schedule["_id"]},
            {"$set": {"lastCompletedDate": now, "nextDueDate": next_due}},
        )

    return {
        "status": "done",
        "schedulesChecked": len(due_schedules),
        "ticketsCreated": len(created),
        "ticketIds": created,
    }


@router.post("/run-lease-renewal-check")
async def run_lease_renewal_check(payload: AdminKeyPayload, windowDays: int = 60):
    check_key(payload.key)
    return await _do_lease_renewal_check(windowDays)


async def _do_lease_renewal_check(windowDays: int = 60):
    """Split out from the HTTP handler above, same pattern as
    _do_late_fee_check, so the background scheduler can call this
    directly. Defaults to the same 60-day window the endpoint already
    used, so scheduled runs behave identically to how this was already
    being triggered manually."""
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(days=windowDays)
    cursor = leases_col.find({
        "renewalStatus": "not_sent",
        "endDate": {"$gte": now, "$lte": cutoff},
    })
    expiring_leases = await cursor.to_list(length=1000)

    notified = []
    for lease in expiring_leases:
        property_id = lease.get("propertyId")
        unit_id = lease.get("unitId")
        end_date_str = lease["endDate"].strftime("%B %d, %Y") if isinstance(lease.get("endDate"), datetime) else str(lease.get("endDate"))

        if property_id and unit_id:
            incentive_note = ""
            if lease.get("renewalIncentiveStatus") == "offered":
                incentive_note = f" We're offering: {lease.get('renewalIncentiveDescription', '')}"
            await notifications_service.notify_unit_resident(
                property_id, unit_id,
                type="lease_expiring",
                title="Your lease is expiring soon",
                body=f"Your lease ends {end_date_str} — contact us about renewal options.{incentive_note}",
                link="/payments",
            )

        assigned_tech = await users_col.find_one({"role": "staff", "assignedProperties": property_id}) if property_id else None
        if assigned_tech:
            await notifications_service.notify_user(
                str(assigned_tech["_id"]),
                type="lease_expiring",
                title=f"Lease renewal needed: Unit {unit_id}",
                body=f"Property {property_id} — lease ends {end_date_str}",
                link="/dashboard",
            )
        else:
            await notifications_service.notify_all_staff(
                type="lease_expiring",
                title=f"Lease renewal needed: Unit {unit_id}",
                body=f"Property {property_id} — lease ends {end_date_str} — no tech assigned to this property yet",
                link="/dashboard",
            )

        await leases_col.update_one({"_id": lease["_id"]}, {"$set": {"renewalStatus": "sent"}})
        notified.append(str(lease["_id"]))

    return {
        "status": "done",
        "leasesChecked": len(expiring_leases),
        "notified": len(notified),
        "leaseIds": notified,
    }


@router.post("/run-payment-reminder-check")
async def run_payment_reminder_check(payload: AdminKeyPayload, windowDays: int = 5):
    check_key(payload.key)
    return await _do_payment_reminder_check(windowDays)


async def _do_payment_reminder_check(windowDays: int = 5):
    """Real multi-channel reminders (in-app + SMS + email via
    payment_reminder_service.py) with a genuine 48h cooldown, replacing
    the old logic that only sent a single in-app notification and
    never reminded again once reminderSent was set. That file existed
    fully built but was never actually called from here - confirmed
    directly by reading this function before this change, which still
    used the old one-shot reminderSent boolean and only ever looked at
    upcoming charges.

    Broadened to cover BOTH upcoming charges (due within windowDays,
    same window this always used) AND already-late charges (dueDate in
    the past) - the old version stopped reminding the moment a charge
    became overdue, which is backwards: a charge that's actually late
    is exactly when repeat reminders matter most. Both groups go
    through the same real payment_reminder_service.reminder_eligible()
    check (48h since lastReminderSentAt, or never reminded) - a
    resident is never messaged more than once every 48 hours
    regardless of which of these two groups their charge falls into."""
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(days=windowDays)
    cursor = payments_col.find({
        "$or": [
            {"dueDate": {"$gte": now, "$lte": cutoff}},  # upcoming
            {"dueDate": {"$lt": now}},                    # already late
        ],
    })
    all_charges = await cursor.to_list(length=2000)

    notified = []
    skipped_cooldown = 0
    channel_totals = {"inApp": 0, "sms": 0, "email": 0}

    for charge in all_charges:
        if charge.get("amountPaid", 0) >= charge.get("amountDue", 0):
            continue  # already paid in full, nothing to remind about
        if not payment_reminder_service.reminder_eligible(charge, now):
            skipped_cooldown += 1
            continue

        result = await payment_reminder_service.send_payment_reminder(charge)
        if result["inApp"]:
            channel_totals["inApp"] += 1
        if result["sms"]["sent"]:
            channel_totals["sms"] += 1
        if result["email"]["sent"]:
            channel_totals["email"] += 1

        await payments_col.update_one(
            {"_id": charge["_id"]},
            {"$set": {"lastReminderSentAt": now, "reminderSent": True}},  # reminderSent kept in sync for any older code/reports still reading it
        )
        notified.append(str(charge["_id"]))

    return {
        "status": "done",
        "chargesChecked": len(all_charges),
        "notified": len(notified),
        "skippedCooldown": skipped_cooldown,
        "channelTotals": channel_totals,
        "chargeIds": notified,
    }


@router.post("/run-autopay-check")
async def run_autopay_check(payload: AdminKeyPayload):
    """The recurring trigger side of ACH autopay - stripe_service.py and
    routers/payments.py's /setup-intent, /autopay/enroll, and
    /stripe-webhook endpoints handle a resident linking a bank account
    and being charged on-demand; this is what actually fires a charge
    automatically once a charge's own dueDate arrives, without the
    resident needing to click anything that day.

    Same external-cron-triggered pattern as run-late-fee-check and
    run-maintenance-check - deliberately not run from inside this app
    on a timer, since Render's free tier has no persistent background
    process to run one.

    Eligibility, deliberately conservative to avoid a double-charge:
    dueDate has arrived (not before - charging early would be a
    genuine surprise to a resident who didn't ask for that), the
    charge isn't already fully paid, and it hasn't already had an
    autopay attempt made against it (autopayAttempted, set here
    regardless of whether that attempt succeeds or fails - a failed
    attempt still needs a human to look at it via /run-payment-
    reminder-check and the delinquent-charges list, not a silent
    automatic retry that could hit an already-known-bad bank account
    repeatedly)."""
    check_key(payload.key)
    return await _do_autopay_check()


async def _do_autopay_check():
    """Split out from the HTTP handler above, same pattern as
    _do_late_fee_check, so the background scheduler can call this
    directly. This is the one check in this file that moves real
    money — kept deliberately conservative (see the handler's own
    docstring above): a failed attempt is surfaced to staff and the
    resident, never silently retried."""
    now = datetime.now(timezone.utc)
    cursor = payments_col.find({
        "dueDate": {"$lte": now},
        "autopayAttempted": {"$ne": True},
    })
    due_charges = await cursor.to_list(length=1000)

    attempted = []
    charged = []
    skipped_no_autopay = 0
    failed = []

    for charge in due_charges:
        remaining_due = charge.get("amountDue", 0) - charge.get("amountPaid", 0)
        if remaining_due <= 0:
            continue  # already paid in full some other way, nothing for autopay to do

        property_id = charge.get("propertyId")
        unit_id = charge.get("unitId")
        resident = await users_col.find_one({
            "role": "tenant", "propertyId": property_id, "unitId": unit_id,
            "autopayEnabled": True,
        })
        if not resident or not resident.get("autopayPaymentMethodId") or not resident.get("stripeCustomerId"):
            skipped_no_autopay += 1
            continue

        # Mark attempted before making the actual charge, not after -
        # if this process crashes or the Render instance restarts
        # mid-run, a retry of this same endpoint must not re-charge a
        # resident whose attempt already went out, even if we never
        # got to record the outcome.
        await payments_col.update_one({"_id": charge["_id"]}, {"$set": {"autopayAttempted": True}})
        attempted.append(str(charge["_id"]))

        try:
            result = await create_ach_payment_intent_async(
                resident["stripeCustomerId"],
                resident["autopayPaymentMethodId"],
                amount_cents=round(remaining_due * 100),
                description=charge.get("description", "Rent payment (autopay)"),
            )
            await payments_col.update_one(
                {"_id": charge["_id"]},
                {"$set": {"stripePaymentIntentId": result["paymentIntentId"], "paymentProcessingStatus": result["status"]}},
            )
            charged.append(str(charge["_id"]))
            await notifications_service.notify_unit_resident(
                property_id, unit_id,
                type="general",
                title="Autopay charge submitted",
                body=f"${remaining_due:.2f} autopay submitted for {charge.get('description', 'your charge')}. "
                     f"ACH payments take a few business days to clear.",
                link="/payments",
            )
        except (StripeNotConfigured, StripePayError) as exc:
            await payments_col.update_one(
                {"_id": charge["_id"]},
                {"$set": {"paymentProcessingStatus": "failed", "autopayError": str(exc)}},
            )
            failed.append(str(charge["_id"]))
            await notifications_service.notify_unit_resident(
                property_id, unit_id,
                type="general",
                title="Autopay charge failed",
                body=f"We couldn't process your autopay charge for {charge.get('description', 'your charge')}. "
                     f"Please check your payment method or pay another way.",
                link="/payments",
            )
            await notifications_service.notify_all_staff(
                type="general",
                title="Autopay charge failed",
                body=f"Unit {unit_id} at property {property_id} — autopay attempt failed: {exc}",
                link="/payments",
            )

    return {
        "status": "done",
        "chargesChecked": len(due_charges),
        "attempted": len(attempted),
        "charged": len(charged),
        "failed": len(failed),
        "skippedNoAutopay": skipped_no_autopay,
        "chargeIds": attempted,
    }


async def _find_property(property_id: str | None) -> dict | None:
    """Property _id may be a real ObjectId or a plain string (e.g. seeded
    demo/scale-test data) — try string first (the common case here), fall
    back to ObjectId only if the string itself looks like a valid one."""
    if not property_id:
        return None
    prop = await properties_col.find_one({"_id": property_id})
    if prop:
        return prop
    if ObjectId.is_valid(property_id):
        return await properties_col.find_one({"_id": ObjectId(property_id)})
    return None


@router.post("/run-late-fee-check")
async def run_late_fee_check(payload: AdminKeyPayload):
    check_key(payload.key)
    return await _do_late_fee_check()


async def _do_late_fee_check():
    """The actual check logic, split out from the HTTP handler above so
    a real background scheduler (see main.py) can call it directly
    without a self-HTTP-call or the admin key — the key exists to gate
    manual/external triggering, not to gate the in-process scheduler
    that already runs inside this same trusted process."""
    now = datetime.now(timezone.utc)
    cursor = payments_col.find({"lateFeeApplied": {"$ne": True}})
    all_unpaid_candidates = await cursor.to_list(length=2000)

    charged = []
    for charge in all_unpaid_candidates:
        if charge.get("amountPaid", 0) >= charge.get("amountDue", 0):
            continue  # already paid, not late
        due_date = charge.get("dueDate")
        if not isinstance(due_date, datetime):
            continue

        property_id = charge.get("propertyId")
        prop = await _find_property(property_id)
        grace_days = (prop or {}).get("lateFeeGraceDays", DEFAULT_LATE_FEE_GRACE_DAYS)
        late_fee_amount = (prop or {}).get("lateFeeAmount", DEFAULT_LATE_FEE_AMOUNT)

        # MongoDB via Motor returns naive datetimes by default (no tzinfo),
        # while `now` here is timezone-aware — subtracting them directly
        # raises TypeError. Normalize both to naive before comparing.
        due_date_naive = due_date.replace(tzinfo=None) if due_date.tzinfo else due_date
        now_naive = now.replace(tzinfo=None)
        if (now_naive - due_date_naive).days < grace_days:
            continue  # still within grace period

        new_amount_due = charge["amountDue"] + late_fee_amount
        await payments_col.update_one(
            {"_id": charge["_id"]},
            {"$set": {"amountDue": new_amount_due, "lateFeeApplied": True, "lateFeeAmount": late_fee_amount}},
        )

        unit_id = charge.get("unitId")

        # A real notice document, not just a fee silently applied.
        # Deliberately factual, not a legal-conclusion document: states
        # what's owed and when, without using jurisdiction-specific
        # legal terms (e.g. "Notice to Quit") or claiming to satisfy
        # any particular state's statutory notice-period requirements -
        # this app's real, multi-state compliance rules (mentioned in
        # project history but confirmed absent from this actual repo,
        # same as the earlier on-call/telephony gap this session found)
        # would need to genuinely exist and be verified correct before
        # a document claiming legal compliance would be honest to
        # generate. A factual notice of the real charge is safe and
        # useful on its own without needing that.
        notice_content = (
            f"This is a notice that a late fee has been applied to your account.\n\n"
            f"Charge: {charge.get('description', 'Rent')}\n"
            f"Original amount due: ${charge['amountDue']:,.2f}\n"
            f"Late fee applied: ${late_fee_amount:,.2f}\n"
            f"New amount due: ${new_amount_due:,.2f}\n"
            f"Original due date: {due_date_naive.strftime('%B %d, %Y')}\n"
            f"Notice date: {now.strftime('%B %d, %Y')}\n\n"
            f"Please contact the property office with any questions about this charge."
        )
        notice_doc = {
            "propertyId": property_id,
            "unitId": unit_id,
            "chargeId": str(charge["_id"]),
            "content": notice_content,
            "amountDue": new_amount_due,
            "createdAt": now,
        }
        await late_notices_col.insert_one(notice_doc)

        if property_id and unit_id:
            await notifications_service.notify_unit_resident(
                property_id, unit_id,
                type="general",
                title="Late fee applied",
                body=f"A ${late_fee_amount:.2f} late fee was added to your {charge.get('description', 'charge')} — new amount due: ${new_amount_due:.2f}",
                link="/payments",
            )

        charged.append(str(charge["_id"]))

    return {
        "status": "done",
        "chargesChecked": len(all_unpaid_candidates),
        "lateFeesApplied": len(charged),
        "chargeIds": charged,
    }


@router.post("/run-escalation-check")
async def run_escalation_check(payload: AdminKeyPayload):
    check_key(payload.key)
    return await _do_escalation_check()


async def _do_escalation_check():
    """Fully automated escalation — deliberately built the same way as
    _do_late_fee_check above, both structurally and philosophically: no
    human triggers this per-tenant, it's one recurring check (called by
    the real background scheduler in main.py) that finds every charge
    that genuinely qualifies and acts on all of them. A charge escalates
    once it's had a late fee applied AND stayed unpaid for
    escalationDays beyond that — a real second automated tier past the
    late-fee stage, not a manual "click to escalate" button. Staff get
    visibility (not a task they must remember to do) via a real AI
    Action, using the exact same schema and status flow as every other
    action in the Actions tab — reviewable, but not a required step for
    the escalation itself to have already happened."""

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    cursor = payments_col.find({"lateFeeApplied": True, "escalated": {"$ne": True}})
    candidates = await cursor.to_list(length=2000)

    escalated = []
    for charge in candidates:
        if charge.get("amountPaid", 0) >= charge.get("amountDue", 0):
            continue  # paid since the late fee was applied — no longer a candidate

        due_date = charge.get("dueDate")
        if not isinstance(due_date, datetime):
            continue
        due_date_naive = due_date.replace(tzinfo=None) if due_date.tzinfo else due_date

        property_id = charge.get("propertyId")
        prop = await _find_property(property_id)
        escalation_days = (prop or {}).get("escalationDays", 10)
        grace_days = (prop or {}).get("lateFeeGraceDays", DEFAULT_LATE_FEE_GRACE_DAYS)

        # Escalation threshold is measured from the ORIGINAL due date, not
        # from when the late fee happened to be applied — the late-fee
        # check itself only runs when triggered, so "when it was applied"
        # is an artifact of scheduling, not a meaningful anchor point.
        if (now - due_date_naive).days < grace_days + escalation_days:
            continue

        await payments_col.update_one(
            {"_id": charge["_id"]},
            {"$set": {"escalated": True, "escalatedAt": now}},
        )

        unit_id = charge.get("unitId")
        days_late = (now - due_date_naive).days
        await ai_actions_col.insert_one({
            "propertyId": property_id,
            "type": "collections_escalation",
            "title": f"Escalated: Unit {unit_id} — {days_late} days past due",
            "priority": "high",
            "rationale": (
                f"${charge.get('amountDue', 0):.2f} owed for {charge.get('description', 'a charge')}, "
                f"{days_late} days past the due date and {escalation_days} days past the late-fee stage "
                f"with no payment — automatically escalated per this property's rent rules."
            ),
            "projectedOutcome": "Direct collections follow-up or payment plan discussion",
            "estimatedValue": charge.get("amountDue", 0),
            "affectedUnitIds": [unit_id] if unit_id else [],
            "confidence": 90,
            "riskLevel": "high",
            "plannedSteps": ["Review resident's full payment history", "Contact resident directly", "Consider a payment plan or further action"],
            "status": "suggested",
            "createdAt": now,
        })

        if property_id and unit_id:
            await notifications_service.notify_unit_resident(
                property_id, unit_id,
                type="general",
                title="Account escalated",
                body=f"Your account for {charge.get('description', 'a charge')} has been escalated due to non-payment. Please contact the office.",
                link="/payments",
            )

        escalated.append(str(charge["_id"]))

    return {
        "status": "done",
        "chargesChecked": len(candidates),
        "escalated": len(escalated),
        "chargeIds": escalated,
    }


@router.post("/run-auto-approve-check")
async def run_auto_approve_check(payload: AdminKeyPayload):
    """External-trigger endpoint for the bounded AI Actions auto-approval
    check — see routers/ai_actions.py's _do_auto_approve_check and its
    own docstring for the actual (deliberately narrow) eligibility rules.
    Same pattern as every other check in this file: this HTTP endpoint
    exists for manual/external-cron triggering; the real background
    scheduler in main.py calls the underlying function directly."""
    check_key(payload.key)
    from routers.ai_actions import _do_auto_approve_check
    return await _do_auto_approve_check()


@router.post("/run-vendor-sla-check")
async def run_vendor_sla_check(payload: AdminKeyPayload):
    """External-trigger endpoint for the vendor SLA acceptance +
    escalation check — see vendor_sla_service.py's own module
    docstring for the real market gap this addresses. Same pattern as
    every other check in this file: this HTTP endpoint exists for
    manual/external-cron triggering; the real background scheduler in
    main.py calls the underlying function directly."""
    check_key(payload.key)
    return await _do_vendor_sla_check()


async def _do_vendor_sla_check():
    """Finds every ticket whose dispatched vendor hasn't confirmed
    within the SLA window and either (a) tries the NEXT vendor in that
    property's preferredVendors list for the ticket's category,
    excluding every vendor that's already been tried and didn't
    respond, or (b) if no further vendor is configured, escalates
    directly to staff with an honest, specific notification — never a
    ticket silently left assigned to a vendor who may never show up."""
    now = datetime.now(timezone.utc)
    cursor = tickets_col.find({
        "vendorAcceptanceStatus": "pending",
        "vendorAcceptanceDeadline": {"$lte": now},
    })
    expired_tickets = await cursor.to_list(length=500)

    reassigned = []
    escalated = []
    for ticket in expired_tickets:
        declined_ids = list(ticket.get("vendorDeclinedIds", []))
        if ticket.get("assignedVendorId"):
            declined_ids.append(ticket["assignedVendorId"])

        next_vendor = await vendor_sla_service.find_next_eligible_vendor(
            ticket.get("propertyId"), ticket.get("category"), exclude_vendor_ids=declined_ids,
        )

        if next_vendor:
            ticket["vendorDeclinedIds"] = declined_ids  # carried through to dispatch_with_sla's own update
            await vendor_sla_service.dispatch_with_sla(str(ticket["_id"]), ticket, next_vendor)
            await notifications_service.notify_all_staff(
                type="general",
                title=f"Reassigned after no response: {ticket.get('title', 'ticket')}",
                body=f"Unit {ticket.get('unitId')} — {ticket.get('assignedVendorName', 'the prior vendor')} "
                     f"didn't confirm in time. Now trying {next_vendor['name']}.",
                link=f"/maintenance/{str(ticket['_id'])}",
            )
            reassigned.append(str(ticket["_id"]))
        else:
            await tickets_col.update_one(
                {"_id": ticket["_id"]},
                {"$set": {"vendorAcceptanceStatus": "expired_escalated", "vendorDeclinedIds": declined_ids}},
            )
            await notifications_service.notify_all_staff(
                type="general",
                title=f"No vendor confirmed: {ticket.get('title', 'ticket')}",
                body=f"Unit {ticket.get('unitId')} — {ticket.get('assignedVendorName', 'the assigned vendor')} "
                     f"did not confirm within the SLA window, and no further preferred vendor is configured "
                     f"for this category. Please reassign manually.",
                link=f"/maintenance/{str(ticket['_id'])}",
            )
            escalated.append(str(ticket["_id"]))

    return {
        "status": "done",
        "checked": len(expired_tickets),
        "reassigned": len(reassigned),
        "escalated": len(escalated),
    }


@router.post("/run-vendor-compliance-check")
async def run_vendor_compliance_check(payload: AdminKeyPayload):
    """External-trigger endpoint for the vendor insurance/license
    expiration check. Same pattern as every other check in this file:
    this HTTP endpoint exists for manual/external-cron triggering; the
    real background scheduler in main.py calls the underlying function
    directly."""
    check_key(payload.key)
    return await _do_vendor_compliance_check()


VENDOR_COMPLIANCE_WINDOW_DAYS = 30


async def _do_vendor_compliance_check():
    """The real, missing other half of GET /api/vendors/expiring-
    compliance (routers/vendors.py) — that endpoint always existed as
    a real, correct on-demand query, but nothing ever called it
    automatically, so staff would only ever learn a vendor's insurance
    or license was expiring if they happened to check manually. Vendor
    auto-dispatch already gates on these same two fields (see
    routers/maintenance.py's create_ticket_document /
    vendor_sla_service.py) — a lapsed vendor silently failing a
    dispatch, with no advance warning, is the real risk this closes.

    Idempotent per real expiration date, not a one-time-ever flag: each
    vendor stores which exact expiresDate it was last alerted for
    (insuranceAlertSentFor / licenseAlertSentFor). If staff renew the
    vendor's paperwork and update the date, that's a genuinely new
    expiration this check has never seen, so it correctly alerts again
    when that new date approaches — a single alert per real deadline,
    not a single alert ever."""
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(days=VENDOR_COMPLIANCE_WINDOW_DAYS)
    vendors = await vendors_col.find({"active": True}).to_list(length=500)

    alerted = []
    for vendor in vendors:
        for date_field, alert_field, label in (
            ("insuranceExpiresDate", "insuranceAlertSentFor", "insurance"),
            ("licenseExpiresDate", "licenseAlertSentFor", "license"),
        ):
            expires = vendor.get(date_field)
            if not isinstance(expires, datetime):
                continue
            expires_aware = expires if expires.tzinfo else expires.replace(tzinfo=timezone.utc)
            if not (now <= expires_aware <= cutoff):
                continue
            if vendor.get(alert_field) == expires_aware:
                continue  # already alerted for this exact expiration date

            days_left = (expires_aware - now).days
            await notifications_service.notify_all_staff(
                type="general",
                title=f"Vendor {label} expiring soon: {vendor.get('name')}",
                body=f"{vendor.get('name')}'s {label} expires in {days_left} day{'s' if days_left != 1 else ''} "
                     f"({expires_aware.strftime('%B %d, %Y')}). Auto-dispatch to this vendor will be blocked once it lapses.",
                link="/vendors",
            )
            await vendors_col.update_one({"_id": vendor["_id"]}, {"$set": {alert_field: expires_aware}})
            alerted.append(f"{vendor.get('name')} ({label})")

    return {
        "status": "done",
        "vendorsChecked": len(vendors),
        "alertsSent": len(alerted),
        "details": alerted,
    }


@router.get("/scheduler-health")
async def scheduler_health_status(user: dict = Depends(require_staff)):
    """Real, current status of both background schedulers — see
    scheduler_health.py's own module docstring for the full reasoning.
    Staff-authenticated (not the shared admin key, which exists for
    external cron triggers) since this is just read-only status info
    a logged-in staff member should be able to check directly, not a
    state-changing action."""
    now = datetime.now(timezone.utc)
    cursor = scheduler_health_col.find({})
    docs = await cursor.to_list(length=10)

    EXPECTED_INTERVALS = {
        "rent_automation_scheduler": 6 * 60 * 60,
        "vendor_sla_scheduler": 15 * 60,
    }

    schedulers = []
    for doc in docs:
        last_heartbeat = doc.get("lastHeartbeatAt")
        gap_seconds = None
        healthy = None
        if isinstance(last_heartbeat, datetime):
            last_heartbeat_aware = last_heartbeat.replace(tzinfo=timezone.utc) if last_heartbeat.tzinfo is None else last_heartbeat
            gap_seconds = (now - last_heartbeat_aware).total_seconds()
            expected = EXPECTED_INTERVALS.get(doc["scheduler"])
            healthy = gap_seconds <= expected * 1.5 if expected else None
        schedulers.append({
            "scheduler": doc["scheduler"],
            "lastHeartbeatAt": last_heartbeat.isoformat() if isinstance(last_heartbeat, datetime) else None,
            "secondsSinceLastHeartbeat": round(gap_seconds) if gap_seconds is not None else None,
            "healthy": healthy,
        })

    return {"schedulers": schedulers}


@router.post("/run-renewal-risk-check")
async def run_renewal_risk_check(payload: AdminKeyPayload):
    """External-trigger endpoint for the staged renewal-risk outreach
    check — see renewal_risk_service.py's own module docstring for the
    real scoring reasoning. Same pattern as every other check in this
    file: this HTTP endpoint exists for manual/external-cron
    triggering; the real background scheduler in main.py calls the
    underlying function directly."""
    check_key(payload.key)
    return await _do_renewal_risk_check()


# Range-based, not exact-day matching - (min_days_exclusive, max_days_inclusive].
# Robust to the scheduler ever missing a cycle (see main.py's own
# scheduler-health module): the FIRST time this check runs after a
# lease crosses below a stage's upper bound, it fires that stage,
# whatever the exact day count happens to be - never silently skipped
# just because the exact target day was missed.
RENEWAL_RISK_STAGES = [
    (60, 90),  # ~90 days out: first, earliest touchpoint
    (30, 60),  # ~60 days out
    (0, 30),   # ~30 days out: last call before expiry
]


async def _do_renewal_risk_check():
    """Finds leases newly inside one of the three real outreach stages
    above (90/60/30 days out) that haven't had that stage's check
    already sent, computes each one's real risk score, and for
    medium/high-risk leases specifically: creates a real, reviewable
    AI Action for staff (same schema/status flow as every other action
    in the Actions tab) AND sends the resident a real notification
    prompting them for the actual 'why' behind their real
    hesitation — not just a generic 'your lease is expiring' reminder,
    which the existing 60-day _do_lease_renewal_check already covers
    on its own, separate schedule. Low-risk leases at any stage are
    marked as checked but get no extra outreach - the existing generic
    reminder is already the right amount of attention for those."""
    now = datetime.now(timezone.utc)
    cursor = leases_col.find({
        "endDate": {"$gte": now, "$lte": now + timedelta(days=91)},
        "renewalStatus": {"$ne": "signed"},
    })
    candidates = await cursor.to_list(length=1000)

    checked = []
    flagged = []
    for lease in candidates:
        days_left = renewal_risk_service.days_until(lease.get("endDate"), now)
        if days_left is None:
            continue

        already_sent = lease.get("renewalRiskStagesSent", [])
        stage = None
        for lower, upper in RENEWAL_RISK_STAGES:
            if lower < days_left <= upper and upper not in already_sent:
                stage = upper
                break
        if stage is None:
            continue

        risk = await renewal_risk_service.compute_renewal_risk(lease)
        await leases_col.update_one({"_id": lease["_id"]}, {"$addToSet": {"renewalRiskStagesSent": stage}})
        checked.append(str(lease["_id"]))

        if risk["riskLevel"] in ("medium", "high"):
            unit_id = lease.get("unitId")
            property_id = lease.get("propertyId")
            factor_summary = "; ".join(f"{f['name']}: {f['detail']}" for f in risk["factors"])

            await ai_actions_col.insert_one({
                "propertyId": property_id,
                "type": "renewal_campaign",
                "title": f"Renewal risk ({risk['riskLevel']}): Unit {unit_id}, {stage} days out",
                "priority": "high" if risk["riskLevel"] == "high" else "medium",
                "rationale": f"Renewal risk score {risk['score']}/100 ({risk['riskLevel']}). {factor_summary}",
                "projectedOutcome": "Direct renewal outreach before this resident's lease decision is made",
                "estimatedValue": lease.get("rent", 0) * 12,
                "affectedUnitIds": [unit_id] if unit_id else [],
                "confidence": 70,  # a real heuristic, not a validated model - see module docstring
                "riskLevel": risk["riskLevel"],
                "plannedSteps": ["Review the real factors behind this score", "Reach out directly, not just an automated reminder", "Consider a real renewal incentive if warranted"],
                "status": "suggested",
                "createdAt": now,
            })

            if property_id and unit_id:
                await notifications_service.notify_unit_resident(
                    property_id, unit_id,
                    type="general",
                    title="How are you feeling about renewing?",
                    body="Your lease is coming up for renewal. We'd genuinely like to know if there's anything we could do better — reply in the app to let us know.",
                    link=f"/app/renewal-checkin/{lease['_id']}",
                )

            flagged.append(str(lease["_id"]))

    return {
        "status": "done",
        "leasesChecked": len(checked),
        "flaggedForOutreach": len(flagged),
        "leaseIds": checked,
    }
