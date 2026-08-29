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

from fastapi import APIRouter, HTTPException
from bson import ObjectId

from db import maintenance_schedules_col, tickets_col, users_col, leases_col, payments_col, properties_col, ai_actions_col
from models import AdminKeyPayload
import notifications_service

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
            await notifications_service.notify_unit_resident(
                property_id, unit_id,
                type="lease_expiring",
                title="Your lease is expiring soon",
                body=f"Your lease ends {end_date_str} — contact us about renewal options",
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

    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(days=windowDays)
    cursor = payments_col.find({
        "dueDate": {"$gte": now, "$lte": cutoff},
        "reminderSent": {"$ne": True},
    })
    upcoming_charges = await cursor.to_list(length=1000)

    notified = []
    for charge in upcoming_charges:
        if charge.get("amountPaid", 0) >= charge.get("amountDue", 0):
            continue  # already paid in full, nothing to remind about

        property_id = charge.get("propertyId")
        unit_id = charge.get("unitId")
        due_str = charge["dueDate"].strftime("%B %d, %Y") if isinstance(charge.get("dueDate"), datetime) else str(charge.get("dueDate"))
        amount_owed = charge.get("amountDue", 0) - charge.get("amountPaid", 0)

        if property_id and unit_id:
            await notifications_service.notify_unit_resident(
                property_id, unit_id,
                type="general",
                title="Upcoming payment due",
                body=f"${amount_owed:.2f} due {due_str} for {charge.get('description', 'your charge')}",
                link="/payments",
            )

        await payments_col.update_one({"_id": charge["_id"]}, {"$set": {"reminderSent": True}})
        notified.append(str(charge["_id"]))

    return {
        "status": "done",
        "chargesChecked": len(upcoming_charges),
        "notified": len(notified),
        "chargeIds": notified,
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
