"""
Lease document AI extraction.

POST /api/lease-extract/extract  -> uploads a signed lease (PDF or
                                     image), real AI analysis extracts
                                     resident/dates/rent/deposit info
                                     as a draft for staff review

Never creates a real lease directly - returns a draft for staff to
review and, if correct, submit through the existing, separate
POST /api/leases (LeaseCreate) themselves. Same "AI drafts, human
confirms before anything real happens" principle already established
in bill_scan.py, whose exact proven pattern this reuses (Cloudinary
upload -> hosted URL -> Claude document/image content block -> strict
JSON-only extraction with honest nulls). Signed leases are commonly
PDFs rather than photos, so unlike bill-scan this also accepts PDF via
the "document" content block (url source - confirmed supported
alongside base64/file_id) rather than only "image".

Deliberately does NOT attempt to resolve the extracted resident/unit
info to a real propertyId/unitId - that match has real consequences
(wrong building/unit gets a lease record) and belongs to staff judgment,
not a guess. The draft is text for staff to read and pick the right
property/unit themselves in the existing lease-creation form.
"""
import os
import json

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from anthropic import AsyncAnthropic
import cloudinary
import cloudinary.uploader

from auth import require_staff

router = APIRouter(prefix="/api/lease-extract", tags=["lease-extract"])

anthropic_client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
MODEL = "claude-sonnet-4-6"

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True,
)

_SYSTEM_PROMPT = """Extract lease information from this real, signed lease document.
Respond with ONLY JSON (no prose, no markdown fences):
{
  "residentName": string or null,
  "residentEmail": string or null,
  "residentPhone": string or null,
  "startDate": "YYYY-MM-DD" or null,
  "endDate": "YYYY-MM-DD" or null,
  "rent": number or null,
  "depositAmount": number or null,
  "propertyNameOnDocument": string or null - the building/property name or address as
    written on the document, for staff to match against the right property themselves,
  "unitNumberOnDocument": string or null - the unit/apartment number as written,
  "confidence": "low" | "medium" | "high",
  "notes": short string - anything about the document that made extraction difficult
    (multi-page, handwritten additions, unclear scan, missing fields, etc.), or null if none
}
If a field genuinely isn't visible or legible, use null for it rather than guessing a
plausible-looking value - this is reviewed by a human before becoming a real lease
record, so an honest null is far better than a confident wrong value."""


@router.post("/extract")
async def extract_lease_data(file: UploadFile = File(...), user: dict = Depends(require_staff)):
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY is not configured")

    content_type = file.content_type or ""
    is_pdf = content_type == "application/pdf"
    is_image = content_type.startswith("image/")
    if not (is_pdf or is_image):
        raise HTTPException(status_code=400, detail="Lease extraction supports PDF or image uploads (photo/scan of the signed lease).")

    file.file.seek(0)
    upload_result = cloudinary.uploader.upload(
        file.file,
        folder="rentflow/lease-scans",
        resource_type="image" if is_image else "raw",
    )
    file_url = upload_result["secure_url"]

    if is_pdf:
        document_block = {"type": "document", "source": {"type": "url", "url": file_url}}
    else:
        document_block = {"type": "image", "source": {"type": "url", "url": file_url}}

    try:
        response = await anthropic_client.messages.create(
            model=MODEL,
            max_tokens=500,
            system=_SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": "Extract the lease information from this document:"},
                    document_block,
                ],
            }],
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI backend error: {exc}") from exc

    raw_text = "".join(block.text for block in response.content if getattr(block, "type", None) == "text")
    try:
        extracted = json.loads(raw_text)
    except json.JSONDecodeError:
        extracted = {
            "residentName": None, "residentEmail": None, "residentPhone": None,
            "startDate": None, "endDate": None, "rent": None, "depositAmount": None,
            "propertyNameOnDocument": None, "unitNumberOnDocument": None,
            "confidence": "low", "notes": "AI response could not be parsed as structured data.",
        }

    return {
        "fileUrl": file_url,
        "extracted": extracted,
        "note": "Review before submitting - this is a draft extraction, not a saved lease. "
                "Pick the correct property and unit yourself, then submit the confirmed values "
                "through the normal Create Lease form to actually create the lease record.",
    }
