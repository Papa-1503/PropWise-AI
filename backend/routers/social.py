"""
Internal staff social feed — announcements, general posts, and peer
recognition ("shoutouts"), plus comments and reactions. Staff-only
(this is an internal comms tool, not resident-facing).

GET  /api/social/posts                    -> feed, newest first
POST /api/social/posts                    -> create a post
POST /api/social/posts/:id/react          -> toggle a reaction (like)
GET  /api/social/posts/:id/comments       -> comments on a post
POST /api/social/posts/:id/comments       -> add a comment

A "shoutout" post (taggedUserId set) also fires a real notification to
the tagged colleague — see notifications_service.py.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends
from bson import ObjectId

from db import posts_col, users_col
from models import PostCreate, CommentCreate
from auth import require_staff
import notifications_service

router = APIRouter(prefix="/api/social/posts", tags=["social"])


async def serialize_post(p: dict, current_user_id: str) -> dict:
    p["id"] = str(p.pop("_id"))
    if isinstance(p.get("createdAt"), datetime):
        p["createdAt"] = p["createdAt"].isoformat()
    reactors = p.pop("reactorIds", [])
    p["reactionCount"] = len(reactors)
    p["reactedByMe"] = current_user_id in reactors
    p["commentCount"] = p.pop("commentCount", 0)
    return p


@router.get("/colleagues")
async def list_colleagues(user: dict = Depends(require_staff)):
    """Lists staff accounts for the shoutout picker — id/name only, no
    sensitive fields."""
    cursor = users_col.find({"role": "staff"}, {"name": 1})
    colleagues = await cursor.to_list(length=200)
    return {"colleagues": [{"id": str(c["_id"]), "name": c["name"]} for c in colleagues if c["_id"] != ObjectId(user["id"])]}


@router.get("")
async def list_posts(category: str | None = None, user: dict = Depends(require_staff)):
    query = {}
    if category:
        query["category"] = category
    cursor = posts_col.find(query).sort("createdAt", -1).limit(100)
    posts = await cursor.to_list(length=100)
    return {"posts": [await serialize_post(p, user["id"]) for p in posts]}


@router.post("")
async def create_post(payload: PostCreate, user: dict = Depends(require_staff)):
    if payload.category == "shoutout" and not payload.taggedUserId:
        raise HTTPException(status_code=400, detail="Shoutout posts must tag a colleague (taggedUserId)")

    tagged_user_name = None
    if payload.taggedUserId:
        if not ObjectId.is_valid(payload.taggedUserId):
            raise HTTPException(status_code=400, detail="Invalid taggedUserId")
        tagged = await users_col.find_one({"_id": ObjectId(payload.taggedUserId)})
        if not tagged:
            raise HTTPException(status_code=404, detail="Tagged user not found")
        tagged_user_name = tagged["name"]

    doc = payload.model_dump()
    doc["authorId"] = user["id"]
    doc["authorName"] = user["name"]
    doc["taggedUserName"] = tagged_user_name
    doc["reactorIds"] = []
    doc["commentCount"] = 0
    doc["createdAt"] = datetime.now(timezone.utc)
    result = await posts_col.insert_one(doc)
    doc["_id"] = result.inserted_id

    if payload.category == "shoutout" and payload.taggedUserId:
        await notifications_service.notify_user(
            payload.taggedUserId,
            type="general",
            title=f"{user['name']} gave you a shoutout! 🎉",
            body=payload.content,
        )

    return await serialize_post(doc, user["id"])


@router.post("/{post_id}/react")
async def toggle_reaction(post_id: str, user: dict = Depends(require_staff)):
    if not ObjectId.is_valid(post_id):
        raise HTTPException(status_code=400, detail="Invalid post ID")
    post = await posts_col.find_one({"_id": ObjectId(post_id)})
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    reactors = post.get("reactorIds", [])
    if user["id"] in reactors:
        await posts_col.update_one({"_id": ObjectId(post_id)}, {"$pull": {"reactorIds": user["id"]}})
    else:
        await posts_col.update_one({"_id": ObjectId(post_id)}, {"$addToSet": {"reactorIds": user["id"]}})

    updated = await posts_col.find_one({"_id": ObjectId(post_id)})
    return await serialize_post(updated, user["id"])


@router.get("/{post_id}/comments")
async def list_comments(post_id: str, user: dict = Depends(require_staff)):
    if not ObjectId.is_valid(post_id):
        raise HTTPException(status_code=400, detail="Invalid post ID")
    post = await posts_col.find_one({"_id": ObjectId(post_id)}, {"comments": 1})
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    comments = post.get("comments", [])
    for c in comments:
        if isinstance(c.get("createdAt"), datetime):
            c["createdAt"] = c["createdAt"].isoformat()
    return {"comments": comments}


@router.post("/{post_id}/comments")
async def add_comment(post_id: str, payload: CommentCreate, user: dict = Depends(require_staff)):
    if not ObjectId.is_valid(post_id):
        raise HTTPException(status_code=400, detail="Invalid post ID")
    post = await posts_col.find_one({"_id": ObjectId(post_id)})
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    comment = {
        "authorId": user["id"],
        "authorName": user["name"],
        "content": payload.content,
        "createdAt": datetime.now(timezone.utc),
    }
    await posts_col.update_one(
        {"_id": ObjectId(post_id)},
        {"$push": {"comments": comment}, "$inc": {"commentCount": 1}},
    )

    # notify the post's author (if someone else commented on their post)
    if post["authorId"] != user["id"]:
        await notifications_service.notify_user(
            post["authorId"],
            type="general",
            title=f"{user['name']} commented on your post",
            body=payload.content,
        )

    comment_out = {**comment, "createdAt": comment["createdAt"].isoformat()}
    return comment_out
