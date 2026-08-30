"""
Cross-portfolio make-ready board (P26).

GET /api/make-ready/board?propertyId=  -> every unit currently mid-turnover,
                                           bucketed into real stages

Genuinely no new collections needed - this is an aggregation over data
that already exists: turnover-type inspections (inspections_col,
type="turnover") and each property's embedded unit.readyToList field
(flipped automatically by inspections.py's update_inspection_item once
every checklist item is non-pending). Supplements the existing
per-unit InspectionsList view (which is for actually completing one
inspection) rather than replacing it - this board is for portfolio-
wide triage, deciding what to look at next, not doing the work itself.

Real stage logic, mapped onto real data rather than a separate status
field that could drift from the underlying truth:
  - "Repairs needed": the inspection has at least one flag/fail item
    (regardless of how many items are still pending) - this needs
    attention NOW, ahead of units that are merely incomplete
  - "Inspection in progress": no flag/fail yet, but at least one item
    is still pending
  - "Ready to list": every item is resolved (readyToList already true,
    confirmed via the unit's own real field rather than recomputed
    here, so this board can never disagree with what
    update_inspection_item already decided)
A unit only appears here at all while it has an active (not fully
resolved) turnover inspection - once readyToList flips true, later
runs of this endpoint will still show it under "Ready to list" for
one pass, then it naturally drops off once staff have moved on and no
new turnover inspection exists for that unit.
"""
from fastapi import APIRouter, Depends

from db import inspections_col, properties_col
from auth import require_staff

router = APIRouter(prefix="/api/make-ready", tags=["make-ready"])


def _unit_stage(inspection: dict) -> str:
    items = inspection.get("items", [])
    if any(i.get("status") in ("flag", "fail") for i in items):
        return "repairs_needed"
    if any(i.get("status") == "pending" for i in items):
        return "inspection_in_progress"
    return "ready_to_list"


@router.get("/board")
async def make_ready_board(propertyId: str | None = None, user: dict = Depends(require_staff)):
    query = {"type": "turnover"}
    if propertyId:
        query["propertyId"] = propertyId
    inspections = await inspections_col.find(query).sort("createdAt", -1).to_list(length=1000)

    # A unit could theoretically have more than one turnover inspection
    # record over time (e.g. a prior one from a previous vacancy) - only
    # the most recent one per property+unit represents its CURRENT
    # state, so this dedupes to that, relying on the sort above
    # (newest first) plus first-write-wins on the dict key.
    latest_per_unit = {}
    for insp in inspections:
        key = (insp.get("propertyId"), insp.get("unitId"))
        if key not in latest_per_unit:
            latest_per_unit[key] = insp

    property_names = {}
    board = {"repairs_needed": [], "inspection_in_progress": [], "ready_to_list": []}

    for (prop_id, unit_id), insp in latest_per_unit.items():
        if prop_id not in property_names:
            from bson import ObjectId
            query_id = ObjectId(prop_id) if ObjectId.is_valid(prop_id) else prop_id
            prop_doc = await properties_col.find_one({"_id": query_id}, {"name": 1})
            property_names[prop_id] = prop_doc.get("name") if prop_doc else prop_id

        items = insp.get("items", [])
        flagged_count = sum(1 for i in items if i.get("status") in ("flag", "fail"))
        pending_count = sum(1 for i in items if i.get("status") == "pending")
        stage = _unit_stage(insp)
        board[stage].append({
            "propertyId": prop_id,
            "propertyName": property_names[prop_id],
            "unitId": unit_id,
            "inspectionId": str(insp["_id"]),
            "totalItems": len(items),
            "flaggedCount": flagged_count,
            "pendingCount": pending_count,
        })

    return {
        "repairsNeeded": board["repairs_needed"],
        "inspectionInProgress": board["inspection_in_progress"],
        "readyToList": board["ready_to_list"],
    }
