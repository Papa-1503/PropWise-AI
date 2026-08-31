"""
Inspection endpoints.

POST /api/inspections                -> create an inspection record
POST /api/inspections/:id/photos     -> upload + attach an annotated photo

Photo storage uses Cloudinary — see save_photo_file() below. Swap
providers by replacing that function only; nothing else needs to change.
"""
import os
import json
import uuid
import base64
import urllib.request
from io import BytesIO
from datetime import datetime, timezone
from xml.sax.saxutils import escape as _xml_escape

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends
from fastapi.responses import StreamingResponse
from bson import ObjectId
from anthropic import AsyncAnthropic
from PIL import Image as PILImage, UnidentifiedImageError
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage, PageBreak
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

from db import inspections_col, photos_col, properties_col, tickets_col, users_col
import notifications_service
from models import InspectionCreate, PhotoAnalysisResult, ItemStatusUpdate
from auth import require_staff

router = APIRouter(prefix="/api/inspections", tags=["inspections"])

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

ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


def save_photo_file(inspection_id: str, upload: UploadFile, safe_ext: str) -> str:
    """Uploads the photo to Cloudinary and returns its permanent URL.

    Local disk isn't durable on Render — it's wiped on every redeploy —
    so photos are stored with Cloudinary instead and only the resulting
    URL is kept in Mongo. safe_ext is still derived from a
    server-validated content-type, not the client filename.
    """
    upload.file.seek(0)
    result = cloudinary.uploader.upload(
        upload.file,
        folder=f"rentflow/inspections/{inspection_id}",
        public_id=uuid.uuid4().hex,
        resource_type="image",
    )
    return result["secure_url"]


def _pdf_text(value) -> str:
    """Escapes text before it goes into a ReportLab Paragraph.

    SECURITY/ROBUSTNESS (found in a live-testing pass): Paragraph()
    interprets its input as a small HTML-like markup language. Any
    user-controlled text (uploaded filename, inspector name, room name,
    unit/property ID) that reached a Paragraph unescaped could break PDF
    generation entirely — confirmed live: a photo uploaded with the
    filename `test<font color="red">evil.jpg` crashed the ENTIRE PDF
    report with an unhandled exception, not just that one photo's
    caption. Every dynamic value must be run through this function
    before being embedded in an f-string passed to Paragraph(). Static
    markup you intend literally (e.g. "&nbsp;|&nbsp;" separators) should
    NOT be passed through this — only the dynamic parts.
    """
    return _xml_escape(str(value) if value is not None else "")


STATUS_LABEL = {"pass": "PASS", "flag": "FLAGGED", "fail": "FAILED", "pending": "PENDING"}
STATUS_COLOR = {
    "pass": colors.HexColor("#059669"),
    "flag": colors.HexColor("#b45309"),
    "fail": colors.HexColor("#b5462f"),
    "pending": colors.HexColor("#94a3b8"),
}


def _fetch_photo_bytes(url: str) -> BytesIO | None:
    """Photo URLs now point to Cloudinary — fetch the bytes so they can
    be embedded in the PDF."""
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            return BytesIO(resp.read())
    except Exception:
        return None


@router.get("/{inspection_id}/pdf")
async def generate_inspection_pdf(inspection_id: str, user: dict = Depends(require_staff)):
    """
    Generates a downloadable PDF inspection report: property/unit header,
    the full checklist with statuses, and any attached photos with their
    click-marked damage points shown as a caption (the mark coordinates
    themselves aren't redrawn onto the image here — see note below).
    """
    if not ObjectId.is_valid(inspection_id):
        raise HTTPException(status_code=400, detail="Invalid inspection ID")

    inspection = await inspections_col.find_one({"_id": ObjectId(inspection_id)})
    if not inspection:
        raise HTTPException(status_code=404, detail="Inspection not found")

    photos = await photos_col.find({"inspectionId": inspection_id}).to_list(length=200)
    photos_by_room: dict[str, list] = {}
    for p in photos:
        photos_by_room.setdefault(p.get("room", ""), []).append(p)

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.6 * inch, bottomMargin=0.6 * inch)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("TitleCustom", parent=styles["Title"], fontSize=18, spaceAfter=4)
    meta_style = ParagraphStyle("Meta", parent=styles["Normal"], textColor=colors.HexColor("#64748b"), fontSize=9)
    room_style = ParagraphStyle("Room", parent=styles["Heading3"], spaceBefore=14, spaceAfter=4)
    caption_style = ParagraphStyle("Caption", parent=styles["Normal"], fontSize=8, textColor=colors.HexColor("#64748b"))

    story = []
    story.append(Paragraph(f"Inspection Report — Unit {_pdf_text(inspection.get('unitId'))}", title_style))
    story.append(Paragraph(
        f"Property: {_pdf_text(inspection.get('propertyId'))} &nbsp;|&nbsp; "
        f"Type: {_pdf_text(inspection.get('type', '').title())} &nbsp;|&nbsp; "
        f"Inspector: {_pdf_text(inspection.get('inspectorName') or 'Unspecified')} &nbsp;|&nbsp; "
        f"Date: {_pdf_text(inspection.get('createdAt').strftime('%B %d, %Y') if inspection.get('createdAt') else 'Unknown')}",
        meta_style,
    ))
    story.append(Spacer(1, 0.25 * inch))

    # Checklist table
    table_data = [["Room", "Description", "Status"]]
    row_colors = []
    for item in inspection.get("items", []):
        table_data.append([
            item.get("room", ""),
            item.get("description", "") or "—",
            STATUS_LABEL.get(item.get("status"), item.get("status", "")),
        ])
        row_colors.append(STATUS_COLOR.get(item.get("status"), colors.black))

    table = Table(table_data, colWidths=[1.3 * inch, 3.9 * inch, 1.0 * inch])
    table_style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#14213d")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
    ]
    for i, c in enumerate(row_colors, start=1):
        table_style.append(("TEXTCOLOR", (2, i), (2, i), c))
        table_style.append(("FONTNAME", (2, i), (2, i), "Helvetica-Bold"))
    table.setStyle(TableStyle(table_style))
    story.append(table)

    # Photos, grouped by room
    if photos_by_room:
        story.append(PageBreak())
        story.append(Paragraph("Photo Documentation", styles["Heading2"]))
        for room, room_photos in photos_by_room.items():
            story.append(Paragraph(_pdf_text(room) or "General", room_style))
            for p in room_photos:
                photo_bytes = _fetch_photo_bytes(p.get("url", ""))
                image_ok = False
                if photo_bytes:
                    # BUG THIS FIXES (found live): reportlab's Image flowable
                    # loads lazily — the file isn't actually read/decoded
                    # until doc.build() runs, which is AFTER any try/except
                    # wrapped around RLImage(...) construction has already
                    # exited. A corrupt or truncated image file (e.g. a
                    # failed/partial upload) would crash the entire PDF
                    # build with an unhandled exception, not just skip that
                    # one photo. Validate the file explicitly, up front,
                    # instead of relying on a try/except that doesn't work.
                    try:
                        photo_bytes.seek(0)
                        with PILImage.open(photo_bytes) as im:
                            im.verify()
                        image_ok = True
                    except (UnidentifiedImageError, OSError):
                        image_ok = False

                if image_ok:
                    photo_bytes.seek(0)
                    story.append(RLImage(photo_bytes, width=3.2 * inch, height=2.4 * inch))
                else:
                    story.append(Paragraph(f"[Image unavailable: {_pdf_text(p.get('originalName'))}]", caption_style))
                mark_count = len(p.get("marks", []))
                safe_name = _pdf_text(p.get("originalName", "photo"))
                story.append(Paragraph(
                    f"{safe_name} — {mark_count} damage point{'s' if mark_count != 1 else ''} marked"
                    if mark_count else safe_name,
                    caption_style,
                ))
                story.append(Spacer(1, 0.15 * inch))

    doc.build(story)
    buffer.seek(0)

    filename = f"inspection_{inspection.get('unitId', 'unit')}_{inspection_id[-6:]}.pdf"
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )



@router.post("/analyze-photo", response_model=PhotoAnalysisResult)
async def analyze_photo(
    file: UploadFile = File(...),
    room: str = Form(""),
    user: dict = Depends(require_staff),
):
    """
    Runs the uploaded photo through Claude's vision to flag visible
    damage/maintenance issues before the inspector finishes typing a
    description — a starting point to review and correct, not a
    substitute for the inspector's own judgment.

    HONESTY NOTE: this is general-purpose vision reasoning, not a model
    trained specifically on property-damage imagery. It can reliably
    call out obvious, clearly-visible issues (visible leaks, cracks,
    stains, damaged fixtures) but can miss issues that aren't visually
    obvious (e.g. a slow leak inside a wall) or misjudge severity. Always
    show this as an editable suggestion, never auto-submit it as the
    inspection record.
    """
    contents = await file.read()
    if len(contents) > 8 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image too large (max 8MB)")
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY is not configured")

    media_type = file.content_type or "image/jpeg"
    if media_type not in ("image/jpeg", "image/png", "image/webp", "image/gif"):
        raise HTTPException(status_code=400, detail=f"Unsupported image type: {media_type}")

    b64_image = base64.standard_b64encode(contents).decode("utf-8")

    system_prompt = """You are assisting a property inspector by reviewing a photo of a
rental unit. Identify any visible maintenance or damage issues ONLY — do not guess at
anything not visibly present in the image. If the room/area looks in good condition,
say so plainly and return an empty issues list rather than inventing minor issues.

Respond with ONLY JSON (no prose, no markdown fences) in this shape:
{
  "summary": "one sentence overall description of what's visible",
  "issues": [
    {"label": "short issue name", "severity": "low"|"medium"|"high", "description": "what's visibly wrong, 1 sentence"}
  ]
}"""

    user_text = f"Room/area: {room or 'unspecified'}. Review this photo for visible issues."

    try:
        response = await anthropic_client.messages.create(
            model=VISION_MODEL,
            max_tokens=500,
            system=system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {"type": "base64", "media_type": media_type, "data": b64_image},
                        },
                        {"type": "text", "text": user_text},
                    ],
                }
            ],
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI vision request failed: {exc}") from exc

    raw = "".join(b.text for b in response.content if getattr(b, "type", None) == "text")
    raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()

    try:
        parsed = json.loads(raw)
        result = PhotoAnalysisResult(**parsed)
    except Exception:
        # Fail soft — a photo the inspector still has and can describe manually
        # is better than a 500 error blocking the whole inspection.
        result = PhotoAnalysisResult(
            summary="AI analysis couldn't parse a result for this photo — please describe manually.",
            issues=[],
        )

    return result


@router.post("")
async def create_inspection(payload: InspectionCreate, user: dict = Depends(require_staff)):
    doc = payload.model_dump()
    doc["createdAt"] = datetime.now(timezone.utc)
    doc["photoIds"] = []
    result = await inspections_col.insert_one(doc)
    return {"inspectionId": str(result.inserted_id)}


@router.post("/{inspection_id}/photos")
async def upload_inspection_photo(
    inspection_id: str,
    file: UploadFile = File(...),
    marks: str = Form("[]"),
    room: str = Form(""),
    itemId: str = Form(""),
    user: dict = Depends(require_staff),
):
    if not ObjectId.is_valid(inspection_id):
        raise HTTPException(status_code=400, detail="Invalid inspection ID")

    inspection = await inspections_col.find_one({"_id": ObjectId(inspection_id)})
    if not inspection:
        raise HTTPException(status_code=404, detail="Inspection not found")

    media_type = file.content_type or ""
    if media_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {media_type or 'unknown'}. Only image uploads are allowed.",
        )

    try:
        parsed_marks = json.loads(marks)
    except json.JSONDecodeError:
        parsed_marks = []

    photo_url = save_photo_file(inspection_id, file, ALLOWED_IMAGE_TYPES[media_type])

    photo_doc = {
        "inspectionId": inspection_id,
        "room": room,
        "itemId": itemId or None,
        # ^ Real, optional link to a specific inspection item -
        # genuinely needed for AB 2801-style photo-documentation
        # requirements (California's real 2025 law requiring photos
        # tied to the SPECIFIC damage a deduction is for, not just any
        # unit photo) - see deposit_pipeline.py's real use of this.
        # Optional and defaulting to None rather than required, since
        # plenty of real inspection photos (general move-in condition
        # shots) genuinely aren't about one specific flagged item.
        "url": photo_url,
        "originalName": file.filename,
        "marks": parsed_marks,  # [{x, y}, ...] — damage points tagged in the UI
        "uploadedAt": datetime.now(timezone.utc),
    }
    result = await photos_col.insert_one(photo_doc)
    photo_id = str(result.inserted_id)

    await inspections_col.update_one(
        {"_id": ObjectId(inspection_id)},
        {"$push": {"photoIds": photo_id}},
    )

    return {"photoId": photo_id, "url": photo_url}


@router.get("/{inspection_id}")
async def get_inspection(inspection_id: str, role: str | None = None, user: dict = Depends(require_staff)):
    """role=maintenance or role=cleaning genuinely scopes the returned
    items to that role only - the real "separate form" behavior
    requested directly: a maintenance tech and a cleaner working the
    same turnover each see only their own real checklist, not the
    other's items mixed in. Both roles' progress lives in the SAME
    underlying inspection record (items each carry their own role tag,
    set at creation - see workflow_actions.py's
    create_turnover_checklist_action), not two separate records that
    could drift out of sync - omitting role returns every item, the
    existing full-detail behavior unchanged for anyone not filtering
    by role."""
    if not ObjectId.is_valid(inspection_id):
        raise HTTPException(status_code=400, detail="Invalid inspection ID")
    inspection = await inspections_col.find_one({"_id": ObjectId(inspection_id)})
    if not inspection:
        raise HTTPException(status_code=404, detail="Inspection not found")
    inspection["_id"] = str(inspection["_id"])
    if role:
        inspection["items"] = [
            item for item in inspection.get("items", [])
            if item.get("role", "maintenance") == role  # backward-compatible default for pre-role items
        ]
    photos = await photos_col.find({"inspectionId": inspection_id}).to_list(length=200)
    for p in photos:
        p["_id"] = str(p["_id"])
    inspection["photos"] = photos
    return inspection

@router.get("")
async def list_inspections(propertyId: str | None = None, unitId: str | None = None, user: dict = Depends(require_staff)):
    query = {}
    if propertyId:
        query["propertyId"] = propertyId
    if unitId:
        query["unitId"] = unitId
    cursor = inspections_col.find(query).sort("createdAt", -1).limit(100)
    results = await cursor.to_list(length=100)
    for r in results:
        r["_id"] = str(r["_id"])
    return {"inspections": results}

@router.patch("/{inspection_id}/items/{item_id}")
async def update_inspection_item(inspection_id: str, item_id: str, payload: ItemStatusUpdate, user: dict = Depends(require_staff)):
    if not ObjectId.is_valid(inspection_id):
        raise HTTPException(status_code=400, detail="Invalid inspection ID")

    inspection = await inspections_col.find_one({"_id": ObjectId(inspection_id)})
    if not inspection:
        raise HTTPException(status_code=404, detail="Inspection not found")

    item = next((i for i in inspection.get("items", []) if i.get("id") == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found on this inspection")

    update_fields = {"items.$.status": payload.status}
    new_ticket_id = None
    effective_description = payload.description if payload.description is not None else item.get("description")
    if payload.description is not None:
        update_fields["items.$.description"] = payload.description

    # Flagging or failing an item auto-generates a maintenance ticket,
    # once per item (won't create duplicates if the item is updated
    # again while already flagged/failed).
    if payload.status in ("flag", "fail") and not item.get("ticketId"):
        ticket = {
            "propertyId": inspection.get("propertyId"),
            "unitId": inspection.get("unitId"),
            "title": effective_description or f"{item.get('room', 'Unit')} issue flagged during inspection",
            "priority": "urgent" if payload.status == "fail" else "normal",
            "source": "inspection",
            "sourceInspectionId": inspection_id,
            "room": item.get("room"),
            "assignee": None,
            "category": "general",
            "status": "open",
            "createdAt": datetime.now(timezone.utc),
        }

        assigned_tech = None
        if inspection.get("propertyId"):
            assigned_tech = await users_col.find_one({"role": "staff", "assignedProperties": inspection["propertyId"]})
        if assigned_tech:
            ticket["assignee"] = assigned_tech.get("email")

        result = await tickets_col.insert_one(ticket)
        new_ticket_id = str(result.inserted_id)
        update_fields["items.$.ticketId"] = new_ticket_id

        if assigned_tech:
            await notifications_service.notify_user(
                str(assigned_tech["_id"]),
                type="urgent_ticket" if payload.status == "fail" else "general",
                title=f"Inspection issue: {ticket['title']}",
                body=f"Unit {inspection.get('unitId')} — flagged during inspection",
                link=f"/maintenance/{new_ticket_id}",
            )
        else:
            await notifications_service.notify_all_staff(
                type="urgent_ticket" if payload.status == "fail" else "general",
                title=f"Inspection issue: {ticket['title']}",
                body=f"Unit {inspection.get('unitId')} — no tech assigned to this property yet",
                link=f"/maintenance/{new_ticket_id}",
            )

    updated = await inspections_col.find_one_and_update(
        {"_id": ObjectId(inspection_id), "items.id": item_id},
        {"$set": update_fields},
        return_document=True,
    )

    if updated.get("type") == "turnover" and updated.get("propertyId") and updated.get("unitId"):
        all_done = all(i.get("status") != "pending" for i in updated.get("items", []))
        await properties_col.update_one(
            {"_id": updated["propertyId"], "units.unitId": updated["unitId"]},
            {"$set": {"units.$.readyToList": all_done}},
        )

    updated["_id"] = str(updated["_id"])
    return updated

