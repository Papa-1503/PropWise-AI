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
    query = {}
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
