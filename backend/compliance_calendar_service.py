"""
State-specific compliance calendar - real deadlines computed from real
lease/inspection data, against rules staff enter for their own
jurisdiction.

CRITICAL, deliberate design decision: this app does NOT hardcode any
state's actual notice-period or deadline requirements anywhere. Two
other places in this codebase already made this same call for the
same reason and say so explicitly - routers/deposit_pipeline.py's
module docstring ("*** NOT LEGAL ADVICE ***... a genuine search of
this repo confirmed the multi-state HUD depreciation engine referenced
in past project history does not actually exist") and
routers/admin.py's late notices ("factual, not legal-conclusion
documents"). Fabricating current, jurisdiction-correct statute numbers
without real legal research would be actively dangerous - a wrong
number here could cause a property manager to violate the exact law
this feature is meant to help them follow, with real legal
consequences neither this app nor its ability to verify current law
can be responsible for.

What this DOES do, safely: lets staff enter their own property's real,
already-known requirements once (ComplianceRulesUpdate, via
PATCH /api/properties/{id}/compliance-rules - state, rentIncreaseNoticeDays,
nonRenewalNoticeDays, depositReturnDeadlineDays), then computes real
deadlines from those numbers against this property's actual lease end
dates and actual move-out inspections. The math is exactly as real and
deterministic as everywhere else in this app; only the legal INPUT
numbers are left to the humans who actually know their own
jurisdiction, exactly like deposit_pipeline.py's usefulLifeYears being
staff-entered rather than guessed.
"""
from datetime import datetime, timedelta, timezone

from db import properties_col, leases_col, inspections_col, documents_col

# How far ahead to look for renewal-notice deadlines - wide enough to
# surface a deadline staff should be planning for now, not so wide
# that the calendar is cluttered with leases many months out.
RENEWAL_HORIZON_DAYS = 120

# How far back to look for a move-out inspection that might still need
# its deposit returned - most state deposit-return deadlines are well
# under this, so a move-out older than this is assumed already handled
# even if no statement was ever generated (rather than surfacing a
# stale deadline from a much older move-out indefinitely).
MOVE_OUT_LOOKBACK_DAYS = 180


async def get_upcoming_deadlines(org_id: str, property_ids: list[str] | None = None) -> list[dict]:
    """Every real, currently-relevant compliance deadline across the
    given properties (or all properties in this org), sorted
    soonest-first. Properties with no compliance rules configured yet
    simply contribute nothing - never a fabricated or default
    deadline. org_id is required and always scopes the underlying
    property query - this was a real, live cross-tenant gap before
    this pass: any staff member of any organization could see every
    other organization's compliance deadlines."""
    now = datetime.now(timezone.utc)
    prop_query: dict = {"orgId": org_id}
    if property_ids:
        prop_query["_id"] = {"$in": property_ids}
    properties = await properties_col.find(prop_query).to_list(length=500)
    props_by_id = {str(p["_id"]): p for p in properties}
    if not props_by_id:
        return []

    deadlines = []

    # 1. Non-renewal notice deadlines - a lease not yet marked "signed"
    # (i.e. renewal not confirmed) whose end date is approaching. If
    # staff plan not to renew, real law in many states requires notice
    # by a certain number of days before the lease actually ends -
    # this surfaces that real deadline, computed from the property's
    # own configured requirement.
    lease_query = {
        "propertyId": {"$in": list(props_by_id.keys())},
        "renewalStatus": {"$ne": "signed"},
        "endDate": {"$lte": now + timedelta(days=RENEWAL_HORIZON_DAYS)},
    }
    leases = await leases_col.find(lease_query).to_list(length=500)
    for lease in leases:
        prop = props_by_id.get(lease.get("propertyId"))
        notice_days = prop.get("nonRenewalNoticeDays") if prop else None
        end_date = lease.get("endDate")
        if not notice_days or not isinstance(end_date, datetime):
            continue
        end_date_aware = end_date if end_date.tzinfo else end_date.replace(tzinfo=timezone.utc)
        notice_deadline = end_date_aware - timedelta(days=notice_days)
        deadlines.append({
            "type": "non_renewal_notice",
            "propertyId": lease.get("propertyId"),
            "propertyName": prop.get("name"),
            "unitId": lease.get("unitId"),
            "residentName": lease.get("residentName"),
            "deadline": notice_deadline.isoformat(),
            "daysUntilDeadline": (notice_deadline - now).days,
            "description": (
                f"Notice deadline if not renewing Unit {lease.get('unitId')} "
                f"(lease ends {end_date_aware.date().isoformat()})"
            ),
        })

    # 2. Deposit return deadlines - a real move-out inspection with no
    # deposit statement generated yet. Uses the inspection's own
    # createdAt as the real move-out reference point, consistent with
    # how routers/deposit_pipeline.py already identifies a move-out
    # (inspection.type == "move-out").
    insp_query = {
        "propertyId": {"$in": list(props_by_id.keys())},
        "type": "move-out",
        "createdAt": {"$gte": now - timedelta(days=MOVE_OUT_LOOKBACK_DAYS)},
    }
    inspections = await inspections_col.find(insp_query).to_list(length=500)
    for insp in inspections:
        prop = props_by_id.get(insp.get("propertyId"))
        deadline_days = prop.get("depositReturnDeadlineDays") if prop else None
        move_out_date = insp.get("createdAt")
        if not deadline_days or not isinstance(move_out_date, datetime):
            continue

        already_generated = await documents_col.find_one({
            "inspectionId": str(insp["_id"]), "documentType": "deposit_statement",
        })
        if already_generated:
            continue

        move_out_aware = move_out_date if move_out_date.tzinfo else move_out_date.replace(tzinfo=timezone.utc)
        return_deadline = move_out_aware + timedelta(days=deadline_days)
        deadlines.append({
            "type": "deposit_return",
            "propertyId": insp.get("propertyId"),
            "propertyName": prop.get("name"),
            "unitId": insp.get("unitId"),
            "deadline": return_deadline.isoformat(),
            "daysUntilDeadline": (return_deadline - now).days,
            "description": (
                f"Deposit return deadline for Unit {insp.get('unitId')} "
                f"(moved out {move_out_aware.date().isoformat()})"
            ),
            "inspectionId": str(insp["_id"]),
        })

    deadlines.sort(key=lambda d: d["deadline"])
    return deadlines
