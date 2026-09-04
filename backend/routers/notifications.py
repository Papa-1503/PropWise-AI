"""
Notification endpoints — read side. See notifications_service.py for how
notifications get created (always server-side, in response to real events).

GET   /api/notifications                  -> list current user's notifications
GET   /api/notifications/unread-count     -> just the count, for a badge
PATCH /api/notifications/:id/read         -> mark one as read
PATCH /api/notifications/read-all         -> mark all as read
"""
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends
from bson import ObjectId

from db import notifications_col
from auth import get_current_user
import translation_service

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


def serialize(n: dict) -> dict:
    n["id"] = str(n.pop("_id"))
    if isinstance(n.get("createdAt"), datetime):
        n["createdAt"] = n["createdAt"].isoformat()
    return n


@router.get("")
async def list_notifications(unreadOnly: bool = False, user: dict = Depends(get_current_user)):
    query = {"userId": user["id"]}
    if unreadOnly:
        query["read"] = False
    cursor = notifications_col.find(query).sort("createdAt", -1).limit(100)
    notifications = [serialize(n) for n in await cursor.to_list(length=100)]

    # Real, on-the-fly translation for a resident with a non-English
    # preference - notifications are stored in English (the canonical
    # language every notify_* call writes in), so the alternative to
    # translating here would be either translating at write time
    # (would require every one of the many notify_* call sites across
    # this app to know the recipient's language ahead of time) or
    # storing a second, always-stale translated copy. Real, but not
    # cached - acceptable for a list capped at 100 items; caching by
    # (notificationId, language) would be a reasonable follow-up if
    # this endpoint's call volume ever made the repeated real API
    # calls a genuine cost concern.
    preferred_language = user.get("preferredLanguage")
    if preferred_language and preferred_language != "en":
        for n in notifications:
            n["title"] = await translation_service.translate_text(n.get("title", ""), preferred_language)
            n["body"] = await translation_service.translate_text(n.get("body", ""), preferred_language)

    return {"notifications": notifications}


@router.get("/unread-count")
async def unread_count(user: dict = Depends(get_current_user)):
    count = await notifications_col.count_documents({"userId": user["id"], "read": False})
    return {"count": count}


@router.patch("/{notification_id}/read")
async def mark_read(notification_id: str, user: dict = Depends(get_current_user)):
    if not ObjectId.is_valid(notification_id):
        raise HTTPException(status_code=400, detail="Invalid notification ID")
    # scoped to the current user so nobody can mark someone else's notification read
    result = await notifications_col.find_one_and_update(
        {"_id": ObjectId(notification_id), "userId": user["id"]},
        {"$set": {"read": True}},
        return_document=True,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Notification not found")
    return serialize(result)


@router.patch("/read-all")
async def mark_all_read(user: dict = Depends(get_current_user)):
    result = await notifications_col.update_many(
        {"userId": user["id"], "read": False}, {"$set": {"read": True}}
    )
    return {"markedRead": result.modified_count}
