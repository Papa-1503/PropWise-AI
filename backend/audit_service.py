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

import sentry_sdk

from db import audit_log_col


async def log_action(
    actor_id: str,
    actor_email: str,
    action: str,
    target_type: str,
    target_id: str | None = None,
    details: dict | None = None,
    org_id: str | None = None,
):
    """Records one audit entry. Never raises - a logging failure should
    never break the actual operation it's describing (same principle as
    notify_all_staff's insert-per-user loop not being allowed to fail
    the action that triggered it). If the audit write itself fails,
    that's a real problem worth knowing about, but it belongs in
    server logs, not as a 500 surfaced to whoever just, say,
    successfully deleted a lease.

    org_id is a real, required-in-practice parameter (multi-tenancy
    pass) - every real call site across the app (leases.py, payments.py,
    properties.py, staff.py, oncall.py, kb.py, budgets.py, supplies.py,
    screening.py, custom_roles.py, rubs.py, smart_locks.py,
    accounting.py, deposit_pipeline.py, telephony.py,
    vendor_acceptance.py) now passes it, so routers/audit.py's
    org-scoped query correctly returns this app's real audit history,
    not just entries created after this parameter was added."""
    try:
        await audit_log_col.insert_one({
            "actorId": actor_id,
            "actorEmail": actor_email,
            "action": action,
            "targetType": target_type,
            "targetId": target_id,
            "details": details or {},
            "orgId": org_id,
            "createdAt": datetime.now(timezone.utc),
        })
    except Exception as exc:
        # Sentry capture added alongside the existing print - found
        # during a comprehensive sweep that every caught-and-printed
        # exception in this app was invisible to Sentry (which only
        # auto-captures UNHANDLED exceptions), the same real class of
        # "silently broken until someone complains" problem the
        # Mailgun misconfiguration earlier this session was. print()
        # is kept too - still useful for local/direct log reading.
        sentry_sdk.capture_exception(exc)
        print(f"Audit log write failed (action={action}, target={target_type}/{target_id}): {exc}")
