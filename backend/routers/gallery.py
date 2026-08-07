"""
Property-wide photo gallery — units, amenities, common areas. Reuses the
same Cloudinary upload pattern as inspection photos (see inspections.py)
so storage stays durable across redeploys.
"""
import os
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends
from bson import ObjectId

import cloudinary
import cloudinary.uploader

from db import gallery_photos_col
from auth import require_staff, get_current_user

router = APIRouter(prefix="/api/gallery", tags=["gallery"])

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True,
)

ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


@router.post("/{property_id}/photos")
async def upload_gallery_photo(
    property_id: str,
    file: UploadFile = File(...),
    caption: str = Form(""),
    user: dict = Depends(require_staff),
):
    media_type = file.content_type or ""
    if media_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {media_type or 'unknown'}")

    file.file.seek(0)
    result = cloudinary.uploader.upload(
        file.file,
        folder=f"rentflow/gallery/{property_id}",
        public_id=uuid.uuid4().hex,
        resource_type="image",
    )

    doc = {
        "propertyId": property_id,
        "url": result["secure_url"],
        "caption": caption,
        "uploadedBy": user.get("name", "Staff"),
        "uploadedAt": datetime.now(timezone.utc),
    }
    inserted = await gallery_photos_col.insert_one(doc)
    return {"photoId": str(inserted.inserted_id), "url": doc["url"]}


@router.get("/{property_id}/photos")
async def list_gallery_photos(property_id: str, user: dict = Depends(get_current_user)):
    cursor = gallery_photos_col.find({"propertyId": property_id}).sort("uploadedAt", -1).limit(200)
    results = await cursor.to_list(length=200)
    for r in results:
        r["_id"] = str(r["_id"])
    return {"photos": results}


@router.delete("/photos/{photo_id}")
async def delete_gallery_photo(photo_id: str, user: dict = Depends(require_staff)):
    if not ObjectId.is_valid(photo_id):
        raise HTTPException(status_code=400, detail="Invalid photo ID")
    result = await gallery_photos_col.delete_one({"_id": ObjectId(photo_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Photo not found")
    return {"status": "deleted"}
