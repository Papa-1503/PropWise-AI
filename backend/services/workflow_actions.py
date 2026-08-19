"""
Action handlers for workflow automation.

Each handler takes (config, payload) and performs one action step.
config = the action's settings from the workflow definition
payload = the event data (e.g. the unit/lease/tenant that triggered it)
"""
from db import tickets_col, notifications_col
from email_service import send_email


async def send_email_action(config: dict, payload: dict):
    to = payload.get("tenantEmail") or payload.get("residentEmail") or payload.get("email")
    if not to:
        raise ValueError("No recipient email found in event payload")
    subject = config.get("subject", "Notification from RentFlow AI")
    body = config.get("body", "")
    await send_email(to=to, subject=subject, body=body)
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
    "assign_user": assign_user_action,
    "set_status": set_status_action,
    "webhook": webhook_action,
}
