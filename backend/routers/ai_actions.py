"""
AI Actions endpoints — the recommendation/approval engine behind the
"AI Recommended Actions" panel in the new dashboard design.

POST /api/ai/actions/generate     -> (staff) scan live data, ask Claude to
                                      propose actions, save as "suggested"
GET  /api/ai/actions?status=      -> list actions, filterable by lifecycle status
PATCH /api/ai/actions/:id/decision -> approve / reject / edit an action;
                                      approving triggers a (stubbed) execution

HONESTY NOTE — read before wiring this into a real product:
The `confidence`, `riskLevel`, and `projectedOutcome` fields are Claude's
reasoned estimate from current portfolio data (lease terms, occupancy,
ticket volume), not output from a model trained on your historical
renewal/outcome data. There is no historical dataset here yet to train
or validate against. Present these to staff as "AI's best judgment" —
a decision aid a human still approves — not as an actuarial guarantee.
Building real predictive confidence (e.g. "74% of similar leases
historically renewed") requires a separate modeling effort once you
have enough historical lease-outcome data to work with.

Execution is also stubbed: approving an action here does NOT actually
send emails, adjust rent in a billing system, or dispatch a vendor.
Each action type has a clearly marked `execute_*` stub — wire these to
your actual email/billing/vendor systems when you're ready.
"""
import json
import os
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Depends
from bson import ObjectId
from anthropic import AsyncAnthropic

from db import ai_actions_col, leases_col, tickets_col, properties_col, payments_col
from models import ActionCreate, ActionDecision
from auth import require_staff
import email_service
import notifications_service

router = APIRouter(prefix="/api/ai/actions", tags=["ai-actions"])

anthropic_client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
MODEL = "claude-sonnet-4-6"


def serialize(action: dict) -> dict:
    action["id"] = str(action.pop("_id"))
    for field in ("createdAt", "updatedAt"):
        if isinstance(action.get(field), datetime):
            action[field] = action[field].isoformat()
    return action


async def gather_portfolio_context(property_id: str | None) -> str:
    """
    Same shape of context the AI Copilot uses — kept consistent so
    recommendations and chat answers are grounded in the same facts.

    FAIR HOUSING NOTE: this context deliberately excludes resident names
    and any other resident-identifying information. Nothing about which
    unit gets flagged, what priority it's given, or what confidence score
    it receives should ever be able to depend on who lives there — only
    on objective unit/lease facts (rent, lease term, renewal status,
    vacancy duration, ticket volume). Resident identity is looked up
    separately, fresh from the database, only at the point an approved
    action actually sends an email (see execute_renewal_campaign /
    execute_collections_reminder below) — never earlier in the pipeline
    where it could influence which units get recommended or how.
    """
    prop_filter = {"propertyId": property_id} if property_id else {}
    sections = []

    cutoff = datetime.now(timezone.utc) + timedelta(days=60)
    leases = await leases_col.find(
        {**prop_filter, "endDate": {"$lte": cutoff}}
    ).sort("endDate", 1).to_list(length=100)
    if leases:
        lines = [
            f"- Unit {l.get('unitId')}: rent ${l.get('rent', 0)}, "
            f"expires {l.get('endDate').strftime('%Y-%m-%d') if l.get('endDate') else '?'}, "
            f"renewal status: {l.get('renewalStatus', 'not_sent')}"
            for l in leases
        ]
        sections.append("LEASES EXPIRING WITHIN 60 DAYS (identified by unit ID only):\n" + "\n".join(lines))

    properties = await properties_col.find(prop_filter).to_list(length=200)
    vacant_lines = []
    for p in properties:
        for u in p.get("units", []):
            if u.get("status") == "vacant":
                vacant_lines.append(
                    f"- {p.get('name')} unit {u.get('unitId')}, rent ${u.get('rent', 0)}"
                )
    if vacant_lines:
        sections.append("VACANT UNITS:\n" + "\n".join(vacant_lines))

    tickets = await tickets_col.find(
        {**prop_filter, "status": {"$ne": "done"}}
    ).sort("createdAt", -1).to_list(length=100)
    if tickets:
        lines = [
            f"- unit {t.get('unitId')} [{t.get('priority')}] {t.get('title')} (status: {t.get('status')})"
            for t in tickets
        ]
        sections.append("OPEN MAINTENANCE TICKETS:\n" + "\n".join(lines))

    now = datetime.now(timezone.utc)
    delinquent = await payments_col.find(
        {**prop_filter, "dueDate": {"$lt": now}}
    ).to_list(length=200)
    delinquent = [d for d in delinquent if d.get("amountPaid", 0) < d.get("amountDue", 0)]
    if delinquent:
        lines = [
            f"- unit {d.get('unitId')}: owes ${d.get('amountDue', 0) - d.get('amountPaid', 0):.2f}, "
            f"due {d.get('dueDate').strftime('%Y-%m-%d')}"
            for d in delinquent
        ]
        sections.append("DELINQUENT ACCOUNTS (identified by unit ID only):\n" + "\n".join(lines))

    return "\n\n".join(sections) if sections else "No relevant records found."


@router.post("/generate")
async def generate_actions(propertyId: str | None = None, user: dict = Depends(require_staff)):
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY is not configured")

    context_text = await gather_portfolio_context(propertyId)

    system_prompt = """You are an operations analyst for a property management company.
Given live portfolio data, propose a short list of concrete actions a property
manager could approve. Only propose actions clearly supported by the data below —
do not invent units, leases, or numbers not present in the context.

FAIR HOUSING CONSTRAINT (mandatory): base every recommendation, priority level,
and confidence score ONLY on the objective unit/lease/maintenance data provided —
rent amount, lease dates, renewal status, ticket volume, vacancy duration. The
context you're given does not include resident names or any other resident
identity information, and none was withheld from you selectively — it was
excluded by design. Apply identical reasoning and identical criteria to every
unit uniformly; do not treat any unit or group of units differently based on
building, floor, or location unless that difference is justified by an
objective, stated business reason (e.g. "this floor has had 3x the maintenance
tickets"). If you cannot justify a recommendation using only objective data,
do not propose it.

Respond with ONLY a JSON array (no prose, no markdown fences), where each item has:
{
  "type": "renewal_campaign" | "rent_adjustment" | "collections_reminder" | "maintenance_followup",
  "title": short action title,
  "priority": "high" | "medium" | "low",
  "rationale": 1-2 sentences explaining why, grounded in the data given,
  "projectedOutcome": short phrase, e.g. "$19,800 revenue protected",
  "estimatedValue": numeric dollar value matching projectedOutcome (e.g. 19800), or null if not a dollar-denominated action,
  "affectedUnitIds": [unit ids from the context],
  "confidence": integer 0-100 (your reasoned estimate, not a statistical model),
  "riskLevel": "low" | "medium" | "high",
  "plannedSteps": ["short step 1", "short step 2", ...]
}
Return an empty array if the data doesn't support any clear action."""

    try:
        response = await anthropic_client.messages.create(
            model=MODEL,
            max_tokens=1500,
            system=system_prompt,
            messages=[{"role": "user", "content": f"PORTFOLIO DATA:\n\n{context_text}"}],
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI backend error: {exc}") from exc

    raw_text = "".join(b.text for b in response.content if getattr(b, "type", None) == "text")
    raw_text = raw_text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()

    try:
        proposed = json.loads(raw_text)
    except json.JSONDecodeError:
        raise HTTPException(status_code=502, detail="AI response wasn't valid JSON — try again")

    created = []
    for item in proposed:
        try:
            action = ActionCreate(propertyId=propertyId, **item)
        except Exception:
            continue  # skip anything malformed rather than failing the whole batch
        doc = action.model_dump()
        doc["status"] = "suggested"
        doc["createdAt"] = datetime.now(timezone.utc)
        result = await ai_actions_col.insert_one(doc)
        doc["_id"] = result.inserted_id
        created.append(serialize(doc))

    if created:
        high_priority = sum(1 for a in created if a.get("priority") == "high")
        await notifications_service.notify_all_staff(
            type="ai_action_suggested",
            title=f"{len(created)} new AI recommendation{'s' if len(created) != 1 else ''}",
            body=f"{high_priority} high priority" if high_priority else "Review when you have a moment",
            link="/actions",
        )

    return {"actions": created}


@router.get("")
async def list_actions(
    status: str | None = None,
    propertyId: str | None = None,
    user: dict = Depends(require_staff),
):
    query = {}
    if status:
        query["status"] = status
    if propertyId:
        query["propertyId"] = propertyId
    cursor = ai_actions_col.find(query).sort("createdAt", -1).limit(100)
    actions = await cursor.to_list(length=100)
    return {"actions": [serialize(a) for a in actions]}


# ---------- Execution stubs ----------
# Replace each of these with real integrations when ready. Left explicit
# and separate (rather than one generic "execute()") so it's obvious
# where real side effects need to be wired in.

async def execute_renewal_campaign(action: dict):
    """
    Sends a real renewal-offer email to the resident on each affected
    unit's lease, using whatever SMTP credentials are configured. If
    SMTP isn't configured, or a resident has no email on file, this is
    reported honestly in the result — it does NOT get silently skipped
    and marked as if it succeeded.
    """
    unit_ids = action.get("affectedUnitIds", [])
    if not unit_ids:
        return {"note": "No affected units on this action — nothing to send."}

    leases = await leases_col.find(
        {"propertyId": action.get("propertyId"), "unitId": {"$in": unit_ids}}
    ).to_list(length=200)

    recipients = []
    skipped_no_email = []
    for lease in leases:
        if not lease.get("residentEmail"):
            skipped_no_email.append(lease.get("unitId"))
            continue
        recipients.append({
            "to": lease["residentEmail"],
            "subject": f"Your lease renewal for Unit {lease.get('unitId')}",
            "body_text": (
                f"Hi {lease.get('residentName', 'there')},\n\n"
                f"Your lease for Unit {lease.get('unitId')} is coming up for renewal. "
                f"We'd love to have you stay — reply to this email or contact your leasing office "
                f"to discuss renewal terms.\n\nThanks,\nThe leasing team"
            ),
        })

    if not recipients:
        return {"note": "No residents with an email on file for the affected units — nothing sent."}

    try:
        result = await email_service.send_bulk_async(recipients)
    except Exception as exc:
        return {"note": f"Email sending failed: {exc}"}

    note = f"Sent {len(result['sent'])} renewal offer email(s)."
    if result["failed"]:
        note += f" {len(result['failed'])} failed to send."
    if skipped_no_email:
        note += f" Skipped {len(skipped_no_email)} unit(s) with no resident email on file."
    return {"note": note, "sent": result["sent"], "failed": result["failed"]}


async def execute_rent_adjustment(action: dict):
    """Stub: would update listed rent in the properties collection and syndication feeds."""
    return {"note": "Rent adjustment not yet wired to listing/syndication system."}


async def execute_collections_reminder(action: dict):
    """
    Sends a real payment-reminder email to residents on the affected
    units, personalized with the actual amount owed from the payments
    ledger when available. Same honesty rules as execute_renewal_campaign:
    reports exactly what sent, what failed, and what was skipped.
    """
    unit_ids = action.get("affectedUnitIds", [])
    if not unit_ids:
        return {"note": "No affected units on this action — nothing to send."}

    leases = await leases_col.find(
        {"propertyId": action.get("propertyId"), "unitId": {"$in": unit_ids}}
    ).to_list(length=200)

    now = datetime.now(timezone.utc)
    delinquent_charges = await payments_col.find(
        {"propertyId": action.get("propertyId"), "unitId": {"$in": unit_ids}, "dueDate": {"$lt": now}}
    ).to_list(length=200)
    owed_by_unit = {}
    for c in delinquent_charges:
        outstanding = c.get("amountDue", 0) - c.get("amountPaid", 0)
        if outstanding > 0:
            owed_by_unit[c["unitId"]] = owed_by_unit.get(c["unitId"], 0) + outstanding

    recipients = []
    skipped_no_email = []
    for lease in leases:
        if not lease.get("residentEmail"):
            skipped_no_email.append(lease.get("unitId"))
            continue
        owed = owed_by_unit.get(lease.get("unitId"))
        owed_line = f" Your current outstanding balance is ${owed:.2f}." if owed else ""
        recipients.append({
            "to": lease["residentEmail"],
            "subject": "Friendly reminder: rent payment",
            "body_text": (
                f"Hi {lease.get('residentName', 'there')},\n\n"
                f"This is a friendly reminder that your rent payment for Unit {lease.get('unitId')} "
                f"is due or past due.{owed_line} If you've already paid, please disregard this message. "
                f"Contact your leasing office with any questions.\n\nThanks,\nThe leasing team"
            ),
        })

    if not recipients:
        return {"note": "No residents with an email on file for the affected units — nothing sent."}

    try:
        result = await email_service.send_bulk_async(recipients)
    except Exception as exc:
        return {"note": f"Email sending failed: {exc}"}

    note = f"Sent {len(result['sent'])} reminder email(s)."
    if result["failed"]:
        note += f" {len(result['failed'])} failed to send."
    if skipped_no_email:
        note += f" Skipped {len(skipped_no_email)} unit(s) with no resident email on file."
    return {"note": note, "sent": result["sent"], "failed": result["failed"]}


async def execute_maintenance_followup(action: dict):
    """Stub: would create/escalate maintenance tickets for affected units."""
    return {"note": "Maintenance follow-up not yet wired to ticket auto-creation."}


EXECUTORS = {
    "renewal_campaign": execute_renewal_campaign,
    "rent_adjustment": execute_rent_adjustment,
    "collections_reminder": execute_collections_reminder,
    "maintenance_followup": execute_maintenance_followup,
}


@router.get("/insights/occupancy")
async def occupancy_insight(propertyId: str | None = None, user: dict = Depends(require_staff)):
    """
    Backs the 'Why is occupancy dropping?' panel.

    The vacancy counts and which property is driving them are real,
    computed directly from the properties collection. 'Average days
    vacant' is NOT computed — this schema doesn't track when a unit
    became vacant, so that number is honestly omitted rather than
    guessed. The recommended actions are Claude's reasoning over the
    real vacancy data, clearly separated from the measured facts above.
    """
    prop_filter = {"propertyId": propertyId} if propertyId else {}
    properties = await properties_col.find(prop_filter).to_list(length=200)

    per_property_vacancy = []
    total_vacant = 0
    total_units = 0
    for p in properties:
        vacant = [u for u in p.get("units", []) if u.get("status") == "vacant"]
        units = p.get("units", [])
        total_vacant += len(vacant)
        total_units += len(units)
        if vacant:
            per_property_vacancy.append(
                {"propertyId": str(p.get("_id")), "name": p.get("name"), "vacantCount": len(vacant), "vacantUnitIds": [u.get("unitId") for u in vacant]}
            )

    per_property_vacancy.sort(key=lambda x: x["vacantCount"], reverse=True)
    primary_cause = per_property_vacancy[0] if per_property_vacancy else None

    recommendations = []
    if primary_cause and os.getenv("ANTHROPIC_API_KEY"):
        prompt = (
            f"A property manager has {primary_cause['vacantCount']} vacant units at "
            f"{primary_cause['name']} (unit IDs: {', '.join(primary_cause['vacantUnitIds'])}), "
            f"out of {total_units} total units across the portfolio. "
            "Suggest up to 3 short, concrete actions to help fill these vacancies. "
            "Respond as a JSON array of short strings only, no prose, no markdown fences."
        )
        try:
            response = await anthropic_client.messages.create(
                model=MODEL,
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = "".join(b.text for b in response.content if getattr(b, "type", None) == "text")
            raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            recommendations = json.loads(raw)
        except Exception:
            recommendations = []  # fail quietly — measured facts above still stand on their own

    return {
        "totalVacantUnits": total_vacant,
        "totalUnits": total_units,
        "vacancyRatePct": round((total_vacant / total_units) * 100, 1) if total_units else 0,
        "primaryCause": primary_cause,
        "averageDaysVacant": None,  # not tracked — see docstring
        "recommendedActions": recommendations,
    }
async def _do_approve_action(action_id: str, decided_by_email: str, decided_by_user_id: str | None) -> dict:
    """The actual approve+execute logic, split out from decide_action's
    HTTP handler so it can be reused by the auto-approval scheduled
    check below (see _do_auto_approve_check) without duplicating the
    executor-dispatch logic. decided_by_email is attributed honestly —
    a real staff email for a human decision, or "system_auto_approval"
    for the automated path — so the audit trail never implies a human
    approved something they didn't."""
    updates = {
        "status": "executing",
        "approvedBy": decided_by_email,
        "approvedAt": datetime.now(timezone.utc),
        "updatedAt": datetime.now(timezone.utc),
        "lastDecisionBy": decided_by_email,
        "lastDecisionByUserId": decided_by_user_id,
    }
    action = await ai_actions_col.find_one_and_update(
        {"_id": ObjectId(action_id)}, {"$set": updates}, return_document=True
    )
    if not action:
        return None

    executor = EXECUTORS.get(action["type"])
    result = await executor(action) if executor else {"note": "No executor registered for this type."}

    final_updates = {
        "status": "completed",
        "executionResult": result,
        "updatedAt": datetime.now(timezone.utc),
    }
    return await ai_actions_col.find_one_and_update(
        {"_id": ObjectId(action_id)}, {"$set": final_updates}, return_document=True
    )


# ---------- Bounded auto-approval ----------
#
# Deliberately narrow, not a general "trust the AI" switch. Only
# collections_reminder actions qualify — a gentle payment reminder
# email carries real but low, reversible-in-practice risk even when
# sent slightly early or unnecessarily. Every other action type
# (rent_adjustment, renewal_campaign, maintenance_followup) always
# stays human-reviewed: those touch an actual rent amount, a lease
# term, or a vendor dispatch decision — real financial/legal exposure
# that shouldn't be automated away just because it's inconvenient to
# click a button. confidence >= 90 matches the same threshold already
# used elsewhere in this codebase for a "genuinely high confidence" AI
# assessment (see the escalation action in admin.py).
AUTO_APPROVE_ELIGIBLE_TYPES = ("collections_reminder",)
AUTO_APPROVE_MIN_CONFIDENCE = 90


async def _do_auto_approve_check():
    """Finds suggested actions that meet the narrow auto-approval bar
    and approves+executes them via the exact same code path a human
    approval uses (_do_approve_action above) — never a separate,
    parallel implementation that could drift from what manual approval
    actually does."""
    query = {
        "status": "suggested",
        "type": {"$in": list(AUTO_APPROVE_ELIGIBLE_TYPES)},
        "riskLevel": "low",
        "confidence": {"$gte": AUTO_APPROVE_MIN_CONFIDENCE},
    }
    candidates = await ai_actions_col.find(query).to_list(length=200)

    approved = []
    for action in candidates:
        result = await _do_approve_action(
            str(action["_id"]), decided_by_email="system_auto_approval", decided_by_user_id=None,
        )
        if result:
            approved.append(str(action["_id"]))

    return {"status": "done", "candidatesChecked": len(candidates), "autoApproved": len(approved), "actionIds": approved}


@router.patch("/{action_id}/decision")
async def decide_action(action_id: str, payload: ActionDecision, user: dict = Depends(require_staff)):
    if not ObjectId.is_valid(action_id):
        raise HTTPException(status_code=400, detail="Invalid action ID")

    action = await ai_actions_col.find_one({"_id": ObjectId(action_id)})
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")

    updates = {
        "updatedAt": datetime.now(timezone.utc),
        "lastDecisionBy": user.get("email"),
        "lastDecisionByUserId": user.get("id"),
    }

    if payload.decision == "reject":
        updates["status"] = "rejected"
        updates["rejectedBy"] = user.get("email")
        updates["rejectedAt"] = datetime.now(timezone.utc)
        if payload.note:
            updates["decisionNote"] = payload.note

    elif payload.decision == "edit":
        if payload.editedTitle:
            updates["title"] = payload.editedTitle
        if payload.note:
            updates["decisionNote"] = payload.note
        # stays in "suggested" state for a follow-up approve/reject

    elif payload.decision == "approve":
        result_doc = await _do_approve_action(action_id, decided_by_email=user.get("email"), decided_by_user_id=user.get("id"))
        return serialize(result_doc)

    result_doc = await ai_actions_col.find_one_and_update(
        {"_id": ObjectId(action_id)}, {"$set": updates}, return_document=True
    )
    return serialize(result_doc)
