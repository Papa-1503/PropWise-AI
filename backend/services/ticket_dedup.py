"""
Shared duplicate-ticket detection, used by both the public ticket-creation
endpoint (routers/maintenance.py) and workflow-triggered ticket creation
(services/workflow_actions.py) — the two separate code paths that both
insert into tickets_col.

Deliberately simple and rule-based (same philosophy as the applicant
screening score in routers/screening.py: transparent, not a statistical
model). "Duplicate" here means the same (property, unit, title) with an
existing OPEN ticket — not the same title across different units, which
is a legitimate case of several real, distinct tickets that should be
grouped for display (see MaintenanceTickets.jsx grouping logic) rather
than prevented from being created.

Real motivating case, found Aug 25, 2026: the "Notify on ticket closed"
workflow creates a "Verify repair quality" ticket on every closed ticket.
If the SAME unit's repair gets verified, re-flagged, and closed again
before the first "Verify repair quality" ticket is resolved, a second
identical one would previously get created with no visibility that it
was a repeat.
"""

from datetime import datetime, timezone, timedelta

from db import tickets_col

# How far back to look for an existing open ticket with the same title.
# Generous window — duplicates from repeated workflow triggers or resident
# resubmissions can be days apart, not just minutes.
DUPLICATE_LOOKBACK_HOURS = 72


async def find_existing_open_duplicate(property_id: str | None, unit_id: str | None, title: str):
    """Returns the existing open ticket dict if one matches, else None.
    Never raises — a lookup failure should never block ticket creation,
    it should just mean no duplicate was found."""
    if not property_id or not unit_id or not title:
        return None
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=DUPLICATE_LOOKBACK_HOURS)
        return await tickets_col.find_one({
            "propertyId": property_id,
            "unitId": unit_id,
            "title": title,
            "status": "open",
            "createdAt": {"$gte": cutoff},
        })
    except Exception:
        return None


async def record_duplicate_occurrence(existing_ticket: dict):
    """Bumps a visible counter on the existing ticket rather than silently
    dropping the duplicate — so staff can see a ticket was about to be
    recreated multiple times, which is itself useful signal (e.g. a
    recurring issue that isn't actually getting fixed)."""
    try:
        await tickets_col.update_one(
            {"_id": existing_ticket["_id"]},
            {"$inc": {"duplicateAttempts": 1}, "$set": {"lastDuplicateAttemptAt": datetime.now(timezone.utc)}},
        )
    except Exception:
        pass
