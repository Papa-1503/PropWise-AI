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

Priority 8 addition: notify_user() now also fans out to push, on top of
the existing in-app notification, for every one of this module's three
entry points automatically (they all funnel through notify_user) — no
per-feature changes needed elsewhere, matching the roadmap's intent.
Push failures never break the in-app notification, which stays the
guaranteed-to-work channel; an individually expired subscription is
cleaned up rather than left to fail silently on every future notification.
"""
from datetime import datetime, timezone

from db import notifications_col, users_col, push_subscriptions_col
import push_service


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

    subs = await push_subscriptions_col.find({"userId": user_id}).to_list(length=10)
    for sub in subs:
        try:
            await push_service.send_push_async(
                {"endpoint": sub["endpoint"], "keys": sub["keys"]}, title, body, link
            )
        except push_service.PushSubscriptionExpired:
            await push_subscriptions_col.delete_one({"_id": sub["_id"]})
        except (push_service.PushNotConfigured, push_service.PushSendError):
            # Not configured yet, or a real send failure — either way,
            # the in-app notification above already succeeded, so this
            # is a degraded (not broken) outcome, not raised further.
            pass


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
