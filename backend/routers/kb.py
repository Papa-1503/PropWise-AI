"""
Staff knowledge base — internal-only searchable SOPs, past issue
resolutions, vendor contacts, troubleshooting guides. Separate from
tenant-facing content entirely (see models.py's KbArticleCreate
docstring for how this differs from DocumentCreate and the tenant FAQ).

GET    /api/kb?q=&category=   -> search/list articles
POST   /api/kb                -> create an article
GET    /api/kb/{article_id}   -> read one article
PATCH  /api/kb/{article_id}   -> edit an article
DELETE /api/kb/{article_id}   -> remove an article

Search is regex-based, matching the exact approach already established
in routers/search.py's global command-palette search - case-insensitive
substring match, not a full-text search engine. Consistent with that
router's own stated reasoning: simple and instant is the right choice
at this app's real scale, not a mismatched second search mechanism for
one feature.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends
from bson import ObjectId

from db import kb_articles_col
from models import KbArticleCreate, KbArticleUpdate
from auth import require_staff
from audit_service import log_action

router = APIRouter(prefix="/api/kb", tags=["knowledge-base"])


def serialize(article: dict) -> dict:
    article = dict(article)
    article["id"] = str(article.pop("_id"))
    for field in ("createdAt", "updatedAt"):
        if isinstance(article.get(field), datetime):
            article[field] = article[field].isoformat()
    return article


@router.post("")
async def create_article(payload: KbArticleCreate, user: dict = Depends(require_staff)):
    doc = payload.model_dump()
    doc["authorEmail"] = user.get("email")
    doc["createdAt"] = datetime.now(timezone.utc)
    doc["updatedAt"] = doc["createdAt"]
    result = await kb_articles_col.insert_one(doc)
    doc["_id"] = result.inserted_id

    await log_action(
        actor_id=str(user["id"]), actor_email=user.get("email", ""),
        action="kb_article_created", target_type="kb_article", target_id=str(result.inserted_id),
        details={"title": payload.title, "category": payload.category},
    )

    return serialize(doc)


@router.get("")
async def list_articles(q: str | None = None, category: str | None = None, user: dict = Depends(require_staff)):
    query = {}
    if category:
        query["category"] = category
    if q and len(q.strip()) >= 2:
        regex = {"$regex": q.strip(), "$options": "i"}
        query["$or"] = [{"title": regex}, {"content": regex}]

    cursor = kb_articles_col.find(query).sort("updatedAt", -1).limit(200)
    articles = await cursor.to_list(length=200)
    return {"articles": [serialize(a) for a in articles]}


@router.get("/{article_id}")
async def get_article(article_id: str, user: dict = Depends(require_staff)):
    if not ObjectId.is_valid(article_id):
        raise HTTPException(status_code=400, detail="Invalid article ID")
    article = await kb_articles_col.find_one({"_id": ObjectId(article_id)})
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    return serialize(article)


@router.patch("/{article_id}")
async def update_article(article_id: str, payload: KbArticleUpdate, user: dict = Depends(require_staff)):
    if not ObjectId.is_valid(article_id):
        raise HTTPException(status_code=400, detail="Invalid article ID")
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    updates["updatedAt"] = datetime.now(timezone.utc)

    result = await kb_articles_col.find_one_and_update(
        {"_id": ObjectId(article_id)}, {"$set": updates}, return_document=True
    )
    if not result:
        raise HTTPException(status_code=404, detail="Article not found")

    await log_action(
        actor_id=str(user["id"]), actor_email=user.get("email", ""),
        action="kb_article_updated", target_type="kb_article", target_id=article_id,
        details={"fields": [k for k in updates if k != "updatedAt"]},
    )

    return serialize(result)


@router.delete("/{article_id}")
async def delete_article(article_id: str, user: dict = Depends(require_staff)):
    if not ObjectId.is_valid(article_id):
        raise HTTPException(status_code=400, detail="Invalid article ID")
    result = await kb_articles_col.delete_one({"_id": ObjectId(article_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Article not found")

    await log_action(
        actor_id=str(user["id"]), actor_email=user.get("email", ""),
        action="kb_article_deleted", target_type="kb_article", target_id=article_id,
    )

    return {"deleted": True}
