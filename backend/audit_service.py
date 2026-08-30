"""
Audit trail / activity log — who did what, to what, when.

A single append-only collection (audit_log_col), written to via
log_action() below, rather than automatic request/response
instrumentation. Deliberately explicit, not automatic: automatic
logging of every request either drowns real signal in noise (every
GET, every list fetch) or silently misses actions that don't look like
typical CRUD (a bulk action, a status transition triggered by a
scheduled job rather than a direct user request). An explicit call at
each meaningful mutation is more code, but it's honest about exactly
what's tracked and what isn't, rather than implying blanket coverage
that doesn't actually exist.

Scope of this pass: real infrastructure (this service, the model, the
query endpoints) wired into a representative, genuinely high-value set
of actions across the app - not literally every mutating endpoint in
all 27 routers, which would be a much larger, separate effort. See
routers/audit.py's module docstring for exactly which actions are
covered as of this commit.
"""
from datetime import datetime, timezone

from db import audit_log_col


async def log_action(
    actor_id: str,
    actor_email: str,
    action: str,
    target_type: str,
    target_id: str | None = None,
    details: dict | None = None,
):
    """Records one audit entry. Never raises - a logging failure should
    never break the actual operation it's describing (same principle as
    notify_all_staff's insert-per-user loop not being allowed to fail
    the action that triggered it). If the audit write itself fails,
    that's a real problem worth knowing about, but it belongs in
    server logs, not as a 500 surfaced to whoever just, say,
    successfully deleted a lease."""
    try:
        await audit_log_col.insert_one({
            "actorId": actor_id,
            "actorEmail": actor_email,
            "action": action,
            "targetType": target_type,
            "targetId": target_id,
            "details": details or {},
            "createdAt": datetime.now(timezone.utc),
        })
    except Exception as exc:
        print(f"Audit log write failed (action={action}, target={target_type}/{target_id}): {exc}")
