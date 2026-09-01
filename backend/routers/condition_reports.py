"""
Tenant photo-based condition monitoring.

    POST /api/condition-reports/baseline           -> staff sets a move-in baseline photo for a unit/room
    POST /api/condition-reports                     -> tenant submits a current photo for their own unit/room
    GET  /api/condition-reports?propertyId=&unitId=  -> staff reviews all reports

Distinct from routers/inspections.py's analyze_photo — that's staff-only,
single-photo issue detection during a scheduled inspection. This is
tenant-submitted, periodic, and compares CURRENT against a stored MOVE-IN
BASELINE, producing a numeric condition score rather than a one-off issue
list. Reuses the same Claude vision call shape as analyze_photo, with a
comparison-specific prompt.

Fails honest, not silent: if no baseline photo exists for a room yet, the
tenant's photo is still stored (so staff has it), but no score is
fabricated — the response says plainly that no baseline is set.
"""
import os
import json
import uuid
import base64
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends
from bson import ObjectId
from anthropic import AsyncAnthropic

from db import unit_baseline_photos_col, condition_reports_col
from models import ConditionReportResult
from auth import require_staff, get_current_user

router = APIRouter(prefix="/api/condition-reports", tags=["condition-reports"])

anthropic_client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
VISION_MODEL = "claude-sonnet-4-6"

import cloudinary
import cloudinary.uploader

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True,
)

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


def _save_photo(folder: str, upload: UploadFile) -> str:
    upload.file.seek(0)
    result = cloudinary.uploader.upload(
        upload.file, folder=folder, public_id=uuid.uuid4().hex, resource_type="image",
    )
    return result["secure_url"]


def _fetch_and_encode(url: str) -> tuple[bytes, str] | None:
    """Downloads a stored photo so it can be sent to Claude vision
    alongside the newly-uploaded one. Returns (base64_bytes, media_type)
    or None on failure — callers must handle a missing/unreachable
    baseline photo without crashing the whole comparison."""
    import urllib.request
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = resp.read()
            content_type = resp.headers.get("Content-Type", "image/jpeg")
        return base64.standard_b64encode(data).decode("utf-8"), content_type
    except Exception:
        return None


@router.post("/baseline")
async def set_baseline_photo(
    propertyId: str = Form(...),
    unitId: str = Form(...),
    room: str = Form(...),
    file: UploadFile = File(...),
    user: dict = Depends(require_staff),
):
    """Staff sets (or replaces) the move-in baseline for one room. Only
    one baseline per property+unit+room — a new upload replaces the old
    one rather than accumulating duplicates."""
    if (file.content_type or "") not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {file.content_type}")

    url = _save_photo(f"rentflow/baseline/{propertyId}/{unitId}", file)

    result = await unit_baseline_photos_col.find_one_and_update(
        {"propertyId": propertyId, "unitId": unitId, "room": room},
        {"$set": {"propertyId": propertyId, "unitId": unitId, "room": room,
                   "url": url, "setAt": datetime.now(timezone.utc), "setBy": user.get("email")}},
        upsert=True, return_document=True,
    )
    result["id"] = str(result.pop("_id"))
    return result


@router.post("")
async def submit_condition_report(
    room: str = Form(...),
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    """Tenant submits a current photo of one room in their own unit. The
    propertyId/unitId are taken from their account — a tenant can never
    submit a report for a unit that isn't theirs."""
    if user["role"] != "tenant":
        raise HTTPException(status_code=403, detail="Only tenants submit condition reports")
    property_id = user.get("propertyId")
    unit_id = user.get("unitId")
    if not property_id or not unit_id:
        raise HTTPException(status_code=400, detail="Your account isn't linked to a unit")

    if (file.content_type or "") not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {file.content_type}")

    current_url = _save_photo(f"rentflow/condition-reports/{property_id}/{unit_id}", file)

    baseline = await unit_baseline_photos_col.find_one({"propertyId": property_id, "unitId": unit_id, "room": room})
    if not baseline:
        doc = {
            "propertyId": property_id, "unitId": unit_id, "room": room,
            "currentPhotoUrl": current_url, "baselinePhotoUrl": None,
            "conditionScore": None, "summary": "No move-in baseline photo is set for this room yet — "
                                                 "photo saved for staff review, but no comparison could be made.",
            "changes": [], "createdAt": datetime.now(timezone.utc),
        }
        result = await condition_reports_col.insert_one(doc)
        doc["_id"] = result.inserted_id
        doc["id"] = str(doc.pop("_id"))
        return doc

    # UploadFile's bytes were already consumed by _save_photo() above, so
    # both images are fetched fresh from their stored Cloudinary URLs for
    # the comparison call — keeps the report's stored URLs as the single
    # source of truth for what was actually compared.

    current_encoded = _fetch_and_encode(current_url)
    baseline_encoded = _fetch_and_encode(baseline["url"])

    if not current_encoded or not baseline_encoded or not os.getenv("ANTHROPIC_API_KEY"):
        doc = {
            "propertyId": property_id, "unitId": unit_id, "room": room,
            "currentPhotoUrl": current_url, "baselinePhotoUrl": baseline["url"],
            "conditionScore": None,
            "summary": "Photo saved, but automatic comparison isn't available right now — a staff member will review manually.",
            "changes": [], "createdAt": datetime.now(timezone.utc),
        }
        result = await condition_reports_col.insert_one(doc)
        doc["_id"] = result.inserted_id
        doc["id"] = str(doc.pop("_id"))
        return doc

    current_b64, current_media = current_encoded
    baseline_b64, baseline_media = baseline_encoded

    system_prompt = """You compare two photos of the same rental unit room: a MOVE-IN
BASELINE photo and a CURRENT photo submitted later by the tenant. Score the room's
condition based on wear, damage, and cleanliness changes visible between the two photos.

conditionScore: 100 = no visible change from baseline. Deduct points for genuine wear,
damage, or cleanliness decline visible in the CURRENT photo that wasn't present in the
BASELINE. Do NOT deduct points for lighting/angle differences between the two photos —
only for real physical changes to the room itself.

Respond with ONLY JSON (no prose, no markdown fences):
{"conditionScore": 0-100, "summary": "one sentence", "changes": [{"item": "short label", "severity": "low"|"medium"|"high"}]}
If nothing has changed, return conditionScore: 100 and an empty changes list."""

    try:
        response = await anthropic_client.messages.create(
            model=VISION_MODEL, max_tokens=400, system=system_prompt,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": "BASELINE (move-in) photo:"},
                    {"type": "image", "source": {"type": "base64", "media_type": baseline_media, "data": baseline_b64}},
                    {"type": "text", "text": "CURRENT photo:"},
                    {"type": "image", "source": {"type": "base64", "media_type": current_media, "data": current_b64}},
                ],
            }],
        )
        raw = "".join(b.text for b in response.content if getattr(b, "type", None) == "text")
        raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        parsed = json.loads(raw)
        result = ConditionReportResult(**parsed)  # validates score is 0-100 via Pydantic
        summary, condition_score, changes = result.summary, result.conditionScore, result.changes
    except Exception:
        summary = "AI comparison couldn't be completed for this photo — a staff member will review manually."
        condition_score = None
        changes = []

    doc = {
        "propertyId": property_id, "unitId": unit_id, "room": room,
        "currentPhotoUrl": current_url, "baselinePhotoUrl": baseline["url"],
        "conditionScore": condition_score, "summary": summary, "changes": changes,
        "createdAt": datetime.now(timezone.utc),
    }
    result = await condition_reports_col.insert_one(doc)
    doc["_id"] = result.inserted_id
    doc["id"] = str(doc.pop("_id"))
    return doc


@router.get("")
async def list_condition_reports(propertyId: str | None = None, unitId: str | None = None, user: dict = Depends(require_staff)):
    query: dict = {}
    if propertyId:
        query["propertyId"] = propertyId
    if unitId:
        query["unitId"] = unitId
    cursor = condition_reports_col.find(query).sort("createdAt", -1).limit(200)
    reports = await cursor.to_list(length=200)
    for r in reports:
        r["id"] = str(r.pop("_id"))
        if isinstance(r.get("createdAt"), datetime):
            r["createdAt"] = r["createdAt"].isoformat()
    return {"reports": reports}
