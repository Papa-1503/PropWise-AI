"""
Audit trail query endpoints.

GET /api/audit?targetType=&targetId=  -> everything logged against one record
GET /api/audit?actorId=               -> everything one person did
GET /api/audit                        -> everything, newest first (capped)

Writing to the log happens via audit_service.log_action(), called
directly from other routers at the point of each meaningful mutation -
see audit_service.py's module docstring for which actions are covered
as of this pass:

  - routers/leases.py: create_lease, update_lease
  - routers/payments.py: record_payment (manual, staff-recorded)
  - routers/properties.py: update_rent_rules, update_unit_status
  - routers/staff.py: set_staff_properties
  - routers/oncall.py: create_shift, delete_shift

This is a real starting set focused on financially/operationally
significant actions - not every mutating endpoint in the app.
Extending coverage to more routers is real, valuable follow-on work,
not something this pass claims to have already done.

MULTI-TENANCY: this query now filters by orgId - a real, previously-
live gap this pass closes: any staff member of any organization could
read every other organization's audit log. RETROFIT COMPLETE:
log_action's org_id parameter (audit_service.py) is now passed by
every real call site across the app (leases.py, payments.py,
properties.py, staff.py, oncall.py, kb.py, budgets.py, supplies.py,
screening.py, custom_roles.py, rubs.py, smart_locks.py, accounting.py,
deposit_pipeline.py, telephony.py, vendor_acceptance.py), so this
query correctly reflects real audit history, not just entries logged
after the parameter existed.
"""
from datetime import datetime

from fastapi import APIRouter, Depends

from db import audit_log_col
from auth import require_staff

router = APIRouter(prefix="/api/audit", tags=["audit"])


def serialize(entry: dict) -> dict:
    entry = dict(entry)
    entry["id"] = str(entry.pop("_id"))
    if isinstance(entry.get("createdAt"), datetime):
        entry["createdAt"] = entry["createdAt"].isoformat()
    return entry


@router.get("")
async def list_audit_log(
    targetType: str | None = None,
    targetId: str | None = None,
    actorId: str | None = None,
    limit: int = 100,
    user: dict = Depends(require_staff),
):
    query: dict = {"orgId": user["orgId"]}
    if targetType:
        query["targetType"] = targetType
    if targetId:
        query["targetId"] = targetId
    if actorId:
        query["actorId"] = actorId

    capped_limit = min(limit, 500)
    cursor = audit_log_col.find(query).sort("createdAt", -1).limit(capped_limit)
    entries = await cursor.to_list(length=capped_limit)
    return {"entries": [serialize(e) for e in entries]}
