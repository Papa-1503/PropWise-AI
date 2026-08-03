"""
Notification creation service.

This is intentionally NOT a router — it's a plain function other routers
import to fire a real notification when something actually happens
(urgent ticket created, vendor assigned, payment received, etc.), kept
separate from routers/notifications.py to avoid circular imports (that
router also needs to read/update notifications, and several other
routers need to create them).

There is no public "create notification" endpoint — notifications are
always a side effect of a real event, triggered server-side.
"""
from datetime import datetime, timezone

from db import notifications_col, users_col


async def notify_user(user_id: str, type: str, title: str, body: str, link: str | None = None):
    await notifications_col.insert_one({
        "userId": user_id,
        "type": type,
        "title": title,
        "body": body,
        "link": link,
        "read": False,
        "createdAt": datetime.now(timezone.utc),
    })


async def notify_all_staff(type: str, title: str, body: str, link: str | None = None):
    """Fans a notification out to every staff account. Fine at small scale
    (a property management team); if your staff roster grows large,
    replace this with a proper broadcast/topic model instead of an
    insert-per-user loop."""
    staff_cursor = users_col.find({"role": "staff"}, {"_id": 1})
    async for staff in staff_cursor:
        await notify_user(str(staff["_id"]), type, title, body, link)


async def notify_unit_resident(property_id: str, unit_id: str, type: str, title: str, body: str, link: str | None = None):
    """Notifies whichever tenant account is bound to this property+unit, if any."""
    resident = await users_col.find_one({"role": "tenant", "propertyId": property_id, "unitId": unit_id})
    if resident:
        await notify_user(str(resident["_id"]), type, title, body, link)
