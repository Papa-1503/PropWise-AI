"""
Action handlers for workflow automation.

Each handler takes (config, payload) and performs one action step.
config = the action's settings from the workflow definition
payload = the event data (e.g. the unit/lease/tenant that triggered it)
"""
import uuid
from datetime import datetime, timezone

from db import tickets_col, inspections_col, users_col, properties_col
from email_service import send_email_async, EmailNotConfigured, EmailSendError
import notifications_service


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
    subject = config.get("subject", "Notification from RentFlow AI")
    body_text = config.get("body", "")
    try:
        await send_email_async(to=to, subject=subject, body_text=body_text)
    except (EmailNotConfigured, EmailSendError) as exc:
        raise RuntimeError(f"Email action failed: {exc}") from exc
    return {"sentTo": to}


async def create_task_action(config: dict, payload: dict):
    ticket = {
        "title": config.get("title", "Automated task"),
        "propertyId": payload.get("propertyId"),
        "unitId": payload.get("unitId"),
        "status": "open",
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
    unit_id = payload.get("unitId")
    if not unit_id:
        raise ValueError("No unitId in event payload")
    return {"assignedTo": config.get("userId"), "unitId": unit_id}


async def set_status_action(config: dict, payload: dict):
    return {"status": config.get("status")}


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
    "set_status": set_status_action,
    "webhook": webhook_action,
}
