"""
Push subscription registration — Priority 8, Step 2.

GET  /api/push/vapid-public-key  -> the public key, for the frontend's
                                     PushManager.subscribe() call
POST /api/push                   -> register a subscription for the
                                     current user (any logged-in role)
DELETE /api/push                 -> unregister (e.g. on notification
                                     permission being revoked)
"""
import os

from fastapi import APIRouter, HTTPException, Depends
from bson import ObjectId

from db import push_subscriptions_col
from models import PushSubscriptionCreate
from auth import get_current_user

router = APIRouter(prefix="/api/push", tags=["push"])


@router.get("/vapid-public-key")
async def get_vapid_public_key():
    """Public by design — this is what the browser needs client-side to
    even create a subscription in the first place, before the backend
    is ever involved. Not a secret, unlike VAPID_PRIVATE_KEY_PEM."""
    key = os.getenv("VAPID_PUBLIC_KEY")
    if not key:
        raise HTTPException(status_code=503, detail="Push notifications aren't configured yet.")
    return {"publicKey": key}


@router.post("")
async def register_subscription(payload: PushSubscriptionCreate, user: dict = Depends(get_current_user)):
    """Upserted on (userId, endpoint) — a user re-subscribing (e.g. after
    clearing site data) with the same endpoint just refreshes the same
    document rather than creating a duplicate."""
    await push_subscriptions_col.update_one(
        {"userId": user["id"], "endpoint": payload.endpoint},
        {"$set": {
            "userId": user["id"],
            "endpoint": payload.endpoint,
            "keys": payload.keys.model_dump(),
        }},
        upsert=True,
    )
    return {"status": "subscribed"}


@router.delete("")
async def unregister_subscription(endpoint: str, user: dict = Depends(get_current_user)):
    await push_subscriptions_col.delete_one({"userId": user["id"], "endpoint": endpoint})
    return {"status": "unsubscribed"}
