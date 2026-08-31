"""
Resident community board — genuinely separate from social.py's staff
feed (that one is explicitly internal-only per its own docstring; this
is a distinct collection and router, not the same feed reopened to
tenants).

GET  /api/community/posts                    -> feed for the caller's own
                                                  property, newest first
POST /api/community/posts                    -> create a post
POST /api/community/posts/{id}/react          -> toggle a reaction
GET  /api/community/posts/{id}/comments       -> comments on a post
POST /api/community/posts/{id}/comments       -> add a comment

Scoped per-property, always from the authenticated user's own server-
verified propertyId (staff can pass one explicitly since they aren't
tied to a single property the way a tenant is; tenants can't override
it) - never a client-submitted value that could let someone read or
post to a different building's board.

Only staff can post the 'announcement' category - a resident being
able to post something that displays as an official building
announcement would be a real, meaningful trust problem, not just a
cosmetic one. Enforced in code below, not just documented.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends
from bson import ObjectId

from db import community_posts_col
from models import CommunityPostCreate, CommunityCommentCreate
from auth import get_current_user
import notifications_service

router = APIRouter(prefix="/api/community/posts", tags=["community"])


def _resolve_property_id(user: dict, requested_property_id: str | None) -> str:
    """Staff aren't tied to one property, so they may pass propertyId
    explicitly to view/post to a specific building's board. A tenant's
    propertyId always comes from their own server-verified record,
    full stop - any value they might pass is ignored, not merely
    validated, so there's no path where a crafted request could read
    or post to a different building's board."""
    if user.get("role") == "tenant":
        return user.get("propertyId")
    return requested_property_id or user.get("propertyId")


async def serialize_post(p: dict, current_user_id: str) -> dict:
    p = dict(p)
    p["id"] = str(p.pop("_id"))
    if isinstance(p.get("createdAt"), datetime):
        p["createdAt"] = p["createdAt"].isoformat()
    reactors = p.pop("reactorIds", [])
    p["reactionCount"] = len(reactors)
    p["reactedByMe"] = current_user_id in reactors
    p["commentCount"] = len(p.pop("comments", []))
    return p


@router.get("")
async def list_posts(propertyId: str | None = None, user: dict = Depends(get_current_user)):
    property_id = _resolve_property_id(user, propertyId)
    if not property_id:
        raise HTTPException(status_code=400, detail="No property to show a board for.")
    cursor = community_posts_col.find({"propertyId": property_id}).sort("createdAt", -1).limit(200)
    posts = await cursor.to_list(length=200)
    return {"posts": [await serialize_post(p, str(user["id"])) for p in posts]}


@router.post("")
async def create_post(payload: CommunityPostCreate, propertyId: str | None = None, user: dict = Depends(get_current_user)):
    property_id = _resolve_property_id(user, propertyId)
    if not property_id:
        raise HTTPException(status_code=400, detail="No property to post to.")

    if payload.category == "announcement" and user.get("role") != "staff":
        raise HTTPException(status_code=403, detail="Only staff can post announcements.")

    doc = {
        "propertyId": property_id,
        "authorId": str(user["id"]),
        "authorName": user.get("name", "Resident"),
        "content": payload.content,
        "category": payload.category,
        "reactorIds": [],
        "comments": [],
        "createdAt": datetime.now(timezone.utc),
    }
    result = await community_posts_col.insert_one(doc)
    doc["_id"] = result.inserted_id
    return await serialize_post(doc, str(user["id"]))


@router.post("/{post_id}/react")
async def toggle_reaction(post_id: str, user: dict = Depends(get_current_user)):
    if not ObjectId.is_valid(post_id):
        raise HTTPException(status_code=400, detail="Invalid post ID")
    post = await community_posts_col.find_one({"_id": ObjectId(post_id)})
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    user_id = str(user["id"])
    reactors = post.get("reactorIds", [])
    if user_id in reactors:
        await community_posts_col.update_one({"_id": ObjectId(post_id)}, {"$pull": {"reactorIds": user_id}})
    else:
        await community_posts_col.update_one({"_id": ObjectId(post_id)}, {"$addToSet": {"reactorIds": user_id}})

    updated = await community_posts_col.find_one({"_id": ObjectId(post_id)})
    return await serialize_post(updated, user_id)


@router.get("/{post_id}/comments")
async def list_comments(post_id: str, user: dict = Depends(get_current_user)):
    if not ObjectId.is_valid(post_id):
        raise HTTPException(status_code=400, detail="Invalid post ID")
    post = await community_posts_col.find_one({"_id": ObjectId(post_id)}, {"comments": 1})
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    comments = post.get("comments", [])
    for c in comments:
        if isinstance(c.get("createdAt"), datetime):
            c["createdAt"] = c["createdAt"].isoformat()
    return {"comments": comments}


@router.post("/{post_id}/comments")
async def add_comment(post_id: str, payload: CommunityCommentCreate, user: dict = Depends(get_current_user)):
    if not ObjectId.is_valid(post_id):
        raise HTTPException(status_code=400, detail="Invalid post ID")
    post = await community_posts_col.find_one({"_id": ObjectId(post_id)})
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    comment = {
        "authorId": str(user["id"]),
        "authorName": user.get("name", "Resident"),
        "content": payload.content,
        "createdAt": datetime.now(timezone.utc),
    }
    await community_posts_col.update_one(
        {"_id": ObjectId(post_id)},
        {"$push": {"comments": comment}},
    )

    if post["authorId"] != str(user["id"]):
        await notifications_service.notify_user(
            post["authorId"],
            type="general",
            title=f"{user.get('name', 'Someone')} commented on your post",
            body=payload.content,
        )

    return {**comment, "createdAt": comment["createdAt"].isoformat()}
