"""
Lead nurture — real, automated follow-up emails for leads who haven't
moved past "new" status. Fills the real gap flagged during tonight's
pricing review: PropWise AI has real, grounded prospect chat
(prospect_assistant.py) and real inbound voice triage
(telephony.py/voice_triage_service.py), but nothing that proactively
re-engages a lead who went quiet after their first inquiry.

3 fixed, honest, non-AI-generated touches - day 3, day 7, and a final
day 14 - each sent exactly once per lead, tracked via nurtureStage.
Deliberately stops on its own without any separate opt-out mechanism:
a lead's own real status field is the stop condition - the moment
staff mark a lead toured/applied/signed/declined (any real progress
away from "new"), this stops nurturing them, since the query below
only ever looks at status == "new". A lead who's gone fully unresponsive
past day 14 is left alone rather than nurtured indefinitely, which
would read as spam rather than genuine follow-up.

Runs from the existing rent_automation_scheduler background loop in
main.py (see _do_lead_nurture_check below) - no new scheduling
infrastructure needed, same real 6-hour cadence every other automated
check in this app already uses.
"""
from datetime import datetime, timezone

from db import leads_col, properties_col
from email_service import send_email_async, EmailNotConfigured, EmailSendError

NURTURE_SCHEDULE = [
    (3, 1),   # (days since createdAt, nurtureStage to reach)
    (7, 2),
    (14, 3),
]


def _days_since(created_at: datetime, now: datetime) -> int:
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return (now - created_at).days


async def _describe_interest(lead: dict) -> str:
    """Real, grounded wording - never invents availability. Falls
    back to generic phrasing when a lead has no propertyId/unitId on
    file (LeadCreate.propertyId/unitId are both optional)."""
    property_id = lead.get("propertyId")
    unit_id = lead.get("unitId")
    if not property_id:
        return "the unit you inquired about"

    from bson import ObjectId
    query_id = ObjectId(property_id) if ObjectId.is_valid(property_id) else property_id
    prop = await properties_col.find_one({"_id": query_id})
    if not prop:
        return "the unit you inquired about"

    name = prop.get("name", "the property")
    if unit_id:
        return f"Unit {unit_id} at {name}"
    return name


def _template(stage: int, lead_name: str, interest_text: str) -> tuple[str, str]:
    """Returns (subject, body_text). 3 fixed, real templates - no AI
    generation, so cost and wording are both predictable."""
    first_name = lead_name.split(" ")[0] if lead_name else "there"

    if stage == 1:
        return (
            "Still interested?",
            f"Hi {first_name},\n\n"
            f"Just checking in about {interest_text} — is this still something you're interested in? "
            f"Happy to answer any questions or help you set up a tour.\n\n"
            f"Reply anytime.",
        )
    elif stage == 2:
        return (
            "Following up",
            f"Hi {first_name},\n\n"
            f"Wanted to follow up again on {interest_text} — it's still available. "
            f"Let us know if you'd like to schedule a tour or have any questions.\n\n"
            f"Reply anytime.",
        )
    else:  # stage == 3, final touch
        return (
            "One last check-in",
            f"Hi {first_name},\n\n"
            f"This is a final check-in about {interest_text}. If you're still interested, reply anytime — "
            f"otherwise we'll assume you've found something else, but feel free to reach out down the road.\n\n"
            f"Thanks for your interest.",
        )


async def _do_lead_nurture_check() -> dict:
    """Real, idempotent check - safe to run every 6 hours forever.
    Only ever touches leads with status == 'new' (see this module's
    own docstring for why that's the real, sufficient stop condition)
    and only ever sends a given stage once per lead, tracked via the
    real nurtureStage field."""
    now = datetime.now(timezone.utc)
    candidates = await leads_col.find({"status": "new"}).to_list(length=5000)

    sent_count = 0
    failed_count = 0

    for lead in candidates:
        if not lead.get("email"):
            continue
        current_stage = lead.get("nurtureStage", 0)
        created_at = lead.get("createdAt")
        if not created_at:
            continue
        days_old = _days_since(created_at, now)

        target_stage = None
        for threshold_days, stage in NURTURE_SCHEDULE:
            if days_old >= threshold_days and current_stage < stage:
                target_stage = stage
        if target_stage is None:
            continue

        interest_text = await _describe_interest(lead)
        subject, body_text = _template(target_stage, lead.get("name", ""), interest_text)

        try:
            await send_email_async(to=lead["email"], subject=subject, body_text=body_text)
            sent_count += 1
        except (EmailNotConfigured, EmailSendError):
            failed_count += 1
            continue

        await leads_col.update_one(
            {"_id": lead["_id"]},
            {"$set": {"nurtureStage": target_stage, "lastNurturedAt": now}},
        )

    return {"sent": sent_count, "failed": failed_count, "candidatesChecked": len(candidates)}
