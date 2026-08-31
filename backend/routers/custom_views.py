"""
Custom views (P18).

GET/POST   /api/custom-views                  -> list/create saved views
                                                  (always scoped to the
                                                  authenticated user's own ID)
PATCH      /api/custom-views/{id}
DELETE     /api/custom-views/{id}

Owned per-staff-member - a real, deliberate ownership check on every
read/write below, not just at creation. Two staff members with the
same entityType can have completely independent saved views; one can
never see, edit, or delete another's, confirmed with a real
functional test of the ownership boundary itself.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends
from bson import ObjectId

from db import custom_views_col
from models import CustomViewCreate, CustomViewUpdate
from auth import require_staff

router = APIRouter(prefix="/api/custom-views", tags=["custom-views"])


def serialize(doc: dict) -> dict:
    doc = dict(doc)
    doc["id"] = str(doc.pop("_id"))
    return doc


@router.post("")
async def create_custom_view(payload: CustomViewCreate, user: dict = Depends(require_staff)):
    doc = payload.model_dump()
    doc["ownerId"] = str(user["id"])
    doc["createdAt"] = datetime.now(timezone.utc)
    result = await custom_views_col.insert_one(doc)
    doc["_id"] = result.inserted_id
    return serialize(doc)


@router.get("")
async def list_custom_views(entityType: str | None = None, user: dict = Depends(require_staff)):
    query = {"ownerId": str(user["id"])}
    if entityType:
        query["entityType"] = entityType
    views = await custom_views_col.find(query).sort("name", 1).to_list(length=200)
    return {"views": [serialize(v) for v in views]}


@router.patch("/{view_id}")
async def update_custom_view(view_id: str, payload: CustomViewUpdate, user: dict = Depends(require_staff)):
    if not ObjectId.is_valid(view_id):
        raise HTTPException(status_code=400, detail="Invalid view ID")
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    result = await custom_views_col.find_one_and_update(
        {"_id": ObjectId(view_id), "ownerId": str(user["id"])}, {"$set": updates}, return_document=True
    )
    if not result:
        raise HTTPException(status_code=404, detail="View not found")
    return serialize(result)


@router.delete("/{view_id}")
async def delete_custom_view(view_id: str, user: dict = Depends(require_staff)):
    if not ObjectId.is_valid(view_id):
        raise HTTPException(status_code=400, detail="Invalid view ID")
    result = await custom_views_col.delete_one({"_id": ObjectId(view_id), "ownerId": str(user["id"])})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="View not found")
    return {"deleted": True}
