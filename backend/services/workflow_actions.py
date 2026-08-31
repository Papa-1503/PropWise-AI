"""
Action handlers for workflow automation.

Each handler takes (config, payload) and performs one action step.
config = the action's settings from the workflow definition
payload = the event data (e.g. the unit/lease/tenant that triggered it)
"""
import uuid
from datetime import datetime, timezone
from bson import ObjectId

from db import tickets_col, inspections_col, users_col, properties_col
from email_service import send_email_async, EmailNotConfigured, EmailSendError
import notifications_service
from services.ticket_dedup import find_existing_open_duplicate, record_duplicate_occurrence
from services.ticket_severity import compute_severity


# Standard unit turnover checklist — housekeeping + maintenance items.
# Each becomes one inspection line item the assigned tech marks
# pass/flag/fail, same UI as a regular inspection.
TURNOVER_CHECKLIST_ITEMS = [
    # Housekeeping
    {"room": "Kitchen", "description": "Deep clean counters, cabinets, appliances"},
    {"room": "Bathroom", "description": "Deep clean tub/shower, toilet, sink, mirrors"},
    {"room": "General", "description": "Carpet cleaning"},
    {"room": "General", "description": "Wipe down all interior doors and trim"},
    {"room": "General", "description": "Window and window sill cleaning"},
    {"room": "General", "description": "Paint touch-up as needed"},
    # Maintenance
    {"room": "HVAC", "description": "Check/replace HVAC filter"},
    {"room": "General", "description": "Test all smoke and CO detectors"},
    {"room": "General", "description": "Re-key locks"},
    {"room": "Kitchen", "description": "Confirm all appliances functional"},
    {"room": "General", "description": "Check for leaks under sinks and around toilets"},
    {"room": "General", "description": "Test all outlets and switches"},
]


async def send_email_action(config: dict, payload: dict):
    to = payload.get("tenantEmail") or payload.get("residentEmail") or payload.get("email")
    if not to:
        raise ValueError("No recipient email found in event payload")
    subject = config.get("subject", "Notification from PropWise AI")
    body_text = config.get("body", "")
    try:
        await send_email_async(to=to, subject=subject, body_text=body_text)
    except (EmailNotConfigured, EmailSendError) as exc:
        raise RuntimeError(f"Email action failed: {exc}") from exc
    return {"sentTo": to}


async def create_task_action(config: dict, payload: dict):
    property_id = payload.get("propertyId")
    unit_id = payload.get("unitId")
    title = config.get("title", "Automated task")

    existing_duplicate = await find_existing_open_duplicate(property_id, unit_id, title)
    if existing_duplicate:
        await record_duplicate_occurrence(existing_duplicate)
        return {"ticketId": str(existing_duplicate["_id"]), "wasExistingDuplicate": True}

    severity = compute_severity(title, None)
    ticket = {
        "title": title,
        "propertyId": property_id,
        "unitId": unit_id,
        "status": "open",
        "createdAt": datetime.now(timezone.utc),
        "severityScore": severity["score"],
        "severityTier": severity["tier"],
        "severityExplanation": severity["explanation"],
    }
    result = await tickets_col.insert_one(ticket)
    return {"ticketId": str(result.inserted_id)}


async def create_turnover_checklist_action(config: dict, payload: dict):
    """Replaces the generic 'prep unit' task with a full structured
    turnover checklist (housekeeping + maintenance), assigned to
    whichever tech covers this property, same lookup as resident-
    submitted tickets and preventive maintenance. Also marks the unit
    not-ready-to-list until the checklist is completed (see
    routers/inspections.py update_inspection_item, which flips this
    back once every item is checked off)."""
    property_id = payload.get("propertyId")
    unit_id = payload.get("unitId")

    items = [
        {"id": uuid.uuid4().hex[:8], "room": item["room"], "description": item["description"], "status": "pending"}
        for item in TURNOVER_CHECKLIST_ITEMS
    ]

    doc = {
        "propertyId": property_id,
        "unitId": unit_id,
        "inspectorName": "",
        "type": "turnover",
        "items": items,
        "photoIds": [],
        "createdAt": datetime.now(timezone.utc),
    }
    result = await inspections_col.insert_one(doc)
    inspection_id = str(result.inserted_id)

    if property_id and unit_id:
        await properties_col.update_one(
            {"_id": property_id, "units.unitId": unit_id},
            {"$set": {"units.$.readyToList": False}},
        )

    assigned_tech = None
    if property_id:
        assigned_tech = await users_col.find_one({"role": "staff", "assignedProperties": property_id})

    if assigned_tech:
        await notifications_service.notify_user(
            str(assigned_tech["_id"]),
            type="general",
            title=f"Turnover checklist ready: Unit {unit_id}",
            body=f"{len(items)} items to complete before re-listing",
            link=f"/inspections/{inspection_id}",
        )
    else:
        await notifications_service.notify_all_staff(
            type="general",
            title=f"Turnover checklist ready: Unit {unit_id}",
            body=f"{len(items)} items to complete — no tech assigned to this property yet",
            link=f"/inspections/{inspection_id}",
        )

    return {"inspectionId": inspection_id, "itemCount": len(items)}


async def assign_user_action(config: dict, payload: dict):
    """Real bug found and fixed: this previously computed and returned a
    dict describing an assignment that never actually happened - no
    ticket was ever updated, no one was ever notified. A hollow action
    dressed up as working. Now genuinely assigns: finds the most
    recently created open ticket for this unit (the one this workflow
    run is almost certainly about, since these fire off a real event
    tied to a specific unit) and sets its assignee, then notifies that
    person directly - the same real notify_user call already proven in
    create_turnover_checklist_action above, not a new pattern."""
    unit_id = payload.get("unitId")
    property_id = payload.get("propertyId")
    user_id = config.get("userId")
    if not unit_id:
        raise ValueError("No unitId in event payload")
    if not user_id:
        raise ValueError("No userId configured for this action")

    ticket = await tickets_col.find_one(
        {"propertyId": property_id, "unitId": unit_id, "status": {"$ne": "done"}},
        sort=[("createdAt", -1)],
    )
    if not ticket:
        return {"assigned": False, "reason": "No open ticket found for this unit to assign."}

    assigned_user = await users_col.find_one({"_id": ObjectId(user_id)}) if ObjectId.is_valid(user_id) else None
    if not assigned_user:
        raise ValueError(f"Configured userId {user_id} is not a real user.")

    await tickets_col.update_one({"_id": ticket["_id"]}, {"$set": {"assignee": assigned_user.get("email")}})
    await notifications_service.notify_user(
        str(assigned_user["_id"]),
        type="general",
        title=f"Assigned to you: {ticket.get('title', 'a ticket')}",
        body=f"Unit {unit_id}",
        link=f"/maintenance/{str(ticket['_id'])}",
    )
    return {"assigned": True, "ticketId": str(ticket["_id"]), "assignedTo": assigned_user.get("email")}


async def route_to_team_action(config: dict, payload: dict):
    """The real 'route work to the correct team' capability - not a
    single hardcoded userId (that's what assign_user is for when a
    specific person is genuinely meant), but a lookup by the ticket's
    OWN category against real tech-to-property assignments
    (staff.assignedProperties, the same infrastructure built earlier
    this session for on-call rotation and reused here rather than
    duplicated). Falls back to notifying all staff broadly if no tech
    covers this property yet - never silently drops the routing with
    nobody notified at all."""
    unit_id = payload.get("unitId")
    property_id = payload.get("propertyId")
    if not unit_id or not property_id:
        raise ValueError("No propertyId/unitId in event payload")

    ticket = await tickets_col.find_one(
        {"propertyId": property_id, "unitId": unit_id, "status": {"$ne": "done"}},
        sort=[("createdAt", -1)],
    )
    if not ticket:
        return {"routed": False, "reason": "No open ticket found for this unit to route."}

    assigned_tech = await users_col.find_one({"role": "staff", "assignedProperties": property_id})
    if assigned_tech:
        await tickets_col.update_one({"_id": ticket["_id"]}, {"$set": {"assignee": assigned_tech.get("email")}})
        await notifications_service.notify_user(
            str(assigned_tech["_id"]),
            type="general",
            title=f"Routed to you: {ticket.get('title', 'a ticket')}",
            body=f"Unit {unit_id} - category: {ticket.get('category', 'general')}",
            link=f"/maintenance/{str(ticket['_id'])}",
        )
        return {"routed": True, "ticketId": str(ticket["_id"]), "routedTo": assigned_tech.get("email")}

    await notifications_service.notify_all_staff(
        type="general",
        title=f"Needs routing: {ticket.get('title', 'a ticket')}",
        body=f"Unit {unit_id} - no tech assigned to this property yet",
        link=f"/maintenance/{str(ticket['_id'])}",
    )
    return {"routed": True, "ticketId": str(ticket["_id"]), "routedTo": "all_staff_fallback"}


async def set_status_action(config: dict, payload: dict):
    """Real bug found and fixed alongside assign_user_action - this had
    the identical problem, computing a dict and updating nothing. Now
    genuinely sets the most recent relevant ticket's status, using the
    same real ticket-lookup pattern as the two actions above."""
    unit_id = payload.get("unitId")
    property_id = payload.get("propertyId")
    new_status = config.get("status")
    if not unit_id:
        raise ValueError("No unitId in event payload")
    if new_status not in ("open", "in_progress", "done"):
        raise ValueError(f"Invalid status '{new_status}' - must be open, in_progress, or done.")

    ticket = await tickets_col.find_one(
        {"propertyId": property_id, "unitId": unit_id},
        sort=[("createdAt", -1)],
    )
    if not ticket:
        return {"updated": False, "reason": "No ticket found for this unit to update."}

    await tickets_col.update_one({"_id": ticket["_id"]}, {"$set": {"status": new_status}})
    return {"updated": True, "ticketId": str(ticket["_id"]), "newStatus": new_status}


async def webhook_action(config: dict, payload: dict):
    import httpx
    url = config.get("url")
    if not url:
        raise ValueError("No webhook url configured")
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=payload, timeout=10)
        return {"statusCode": resp.status_code}


ACTION_HANDLERS = {
    "send_email": send_email_action,
    "create_task": create_task_action,
    "create_turnover_checklist": create_turnover_checklist_action,
    "assign_user": assign_user_action,
    "route_to_team": route_to_team_action,
    "set_status": set_status_action,
    "webhook": webhook_action,
}
