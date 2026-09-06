"""
Package/delivery tracking with OCR.

POST /api/packages/log-with-photo   -> uploads a package label photo,
                                        real OCR extraction attempts to
                                        read unit/resident name, staff
                                        reviews/corrects before saving
POST /api/packages                  -> log a package directly (no photo,
                                        or OCR was wrong/illegible)
GET  /api/packages                  -> list packages, filterable by
                                        property/pickedUp status
POST /api/packages/{id}/pickup      -> mark picked up

OCR is a real assist, not an autonomous action - it never creates the
package record itself. The staff member reviews the extracted
unit/name (or types their own if OCR got it wrong or the label wasn't
legible) before the record is actually created via the standard
POST /api/packages endpoint. This matches the same "AI drafts, human
confirms" principle used for bill scan, write-with-AI, and DIY
troubleshooting elsewhere in this app.

MULTI-TENANCY: every package carries a real orgId, stamped server-side
from the creating staff member's own orgId - never client-submitted.
Every query below is scoped by orgId.
"""
import os
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from anthropic import AsyncAnthropic
from bson import ObjectId
import cloudinary
import cloudinary.uploader

from db import packages_col
from models import PackageLogCreate, PackagePickup
from auth import require_staff
import notifications_service

router = APIRouter(prefix="/api/packages", tags=["packages"])

anthropic_client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
MODEL = "claude-sonnet-4-6"

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True,
)


def serialize(doc: dict) -> dict:
    doc = dict(doc)
    doc["id"] = str(doc.pop("_id"))
    return doc


@router.post("/log-with-photo")
async def extract_package_label(file: UploadFile = File(...), user: dict = Depends(require_staff)):
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY is not configured")

    content_type = file.content_type or ""
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Package label scan supports image uploads only.")

    file.file.seek(0)
    upload_result = cloudinary.uploader.upload(file.file, folder="rentflow/packages", resource_type="image")
    image_url = upload_result["secure_url"]

    system_prompt = """Read this package label photo. Respond with ONLY JSON (no prose, no markdown fences):
{
  "residentName": string or null,
  "unitId": string or null,
  "carrier": one of "USPS", "UPS", "FedEx", "Amazon", "other", or null if not identifiable,
  "confidence": "low" | "medium" | "high"
}
Use null for anything not legible or not present - a human reviews this before it's saved, so an
honest null is far better than a guessed value."""

    try:
        response = await anthropic_client.messages.create(
            model=MODEL,
            max_tokens=200,
            system=system_prompt,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": "Read this package label:"},
                    {"type": "image", "source": {"type": "url", "url": image_url}},
                ],
            }],
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI backend error: {exc}") from exc

    raw_text = "".join(block.text for block in response.content if getattr(block, "type", None) == "text")
    import json
    try:
        extracted = json.loads(raw_text)
    except json.JSONDecodeError:
        extracted = {"residentName": None, "unitId": None, "carrier": None, "confidence": "low"}

    return {"imageUrl": image_url, "extracted": extracted}


@router.post("")
async def log_package(payload: PackageLogCreate, user: dict = Depends(require_staff)):
    doc = payload.model_dump()
    doc["orgId"] = user["orgId"]
    doc["pickedUp"] = False
    doc["pickedUpBy"] = None
    doc["pickedUpAt"] = None
    doc["loggedAt"] = datetime.now(timezone.utc)
    result = await packages_col.insert_one(doc)
    doc["_id"] = result.inserted_id

    if payload.unitId:
        await notifications_service.notify_unit_resident(
            payload.propertyId, payload.unitId,
            type="general",
            title="You have a package",
            body=f"A package{f' from {payload.carrier}' if payload.carrier else ''} has arrived for you.",
            link="/packages",
        )

    return serialize(doc)


@router.get("")
async def list_packages(propertyId: str | None = None, pickedUp: bool | None = None, user: dict = Depends(require_staff)):
    query: dict = {"orgId": user["orgId"]}
    if propertyId:
        query["propertyId"] = propertyId
    if pickedUp is not None:
        query["pickedUp"] = pickedUp
    packages = await packages_col.find(query).sort("loggedAt", -1).to_list(length=500)
    return {"packages": [serialize(p) for p in packages]}


@router.post("/{package_id}/pickup")
async def mark_picked_up(package_id: str, payload: PackagePickup, user: dict = Depends(require_staff)):
    if not ObjectId.is_valid(package_id):
        raise HTTPException(status_code=400, detail="Invalid package ID")
    result = await packages_col.find_one_and_update(
        {"_id": ObjectId(package_id), "orgId": user["orgId"]},
        {"$set": {"pickedUp": True, "pickedUpBy": payload.pickedUpBy, "pickedUpAt": datetime.now(timezone.utc)}},
        return_document=True,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Package not found")
    return serialize(result)
