"""
AI bill scan (P18).

POST /api/bill-scan/extract  -> uploads a bill image/PDF, real vision
                                 analysis extracts vendor/amount/date/
                                 category as a draft for staff review

Never creates a real financial record directly - returns a draft
staff review and, if correct, submit through the existing, separate
POST /api/reconciliation (BankLineCreate) themselves, the same "AI
drafts, human confirms before anything real happens" principle
already established for DIY troubleshooting guidance, fraud-detection
flags, and write-with-AI drafts. A wrong amount or vendor extracted
from a blurry photo becoming a real, unreviewed financial ledger entry
would be a genuine, real-world mistake this deliberately doesn't risk.
"""
import os
import json

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from anthropic import AsyncAnthropic
import cloudinary
import cloudinary.uploader

from auth import require_staff

router = APIRouter(prefix="/api/bill-scan", tags=["bill-scan"])

anthropic_client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
MODEL = "claude-sonnet-4-6"

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True,
)


@router.post("/extract")
async def extract_bill_data(file: UploadFile = File(...), user: dict = Depends(require_staff)):
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY is not configured")

    content_type = file.content_type or ""
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Bill scan currently supports image uploads only (not PDF) - take a photo or screenshot of the bill.")

    file.file.seek(0)
    upload_result = cloudinary.uploader.upload(file.file, folder="rentflow/bill-scans", resource_type="image")
    image_url = upload_result["secure_url"]

    system_prompt = """Extract billing information from this image of a real utility or vendor
bill. Respond with ONLY JSON (no prose, no markdown fences):
{
  "vendorName": string or null,
  "amount": number or null,
  "billDate": "YYYY-MM-DD" or null,
  "category": one of "water", "sewer", "trash", "electric", "gas", "other" - your best
    guess from the bill's content, or "other" if unclear,
  "confidence": "low" | "medium" | "high",
  "notes": short string - anything about the image that made extraction
    difficult (blurry, cut off, handwritten, etc.), or null if none
}
If a field genuinely isn't visible or legible, use null for it rather than guessing a
plausible-looking value - this is reviewed by a human before becoming a real financial
record, so an honest null is far better than a confident wrong number."""

    try:
        response = await anthropic_client.messages.create(
            model=MODEL,
            max_tokens=400,
            system=system_prompt,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": "Extract the billing information from this bill:"},
                    {"type": "image", "source": {"type": "url", "url": image_url}},
                ],
            }],
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI backend error: {exc}") from exc

    raw_text = "".join(block.text for block in response.content if getattr(block, "type", None) == "text")
    try:
        extracted = json.loads(raw_text)
    except json.JSONDecodeError:
        extracted = {"vendorName": None, "amount": None, "billDate": None, "category": "other", "confidence": "low", "notes": "AI response could not be parsed as structured data."}

    return {
        "imageUrl": image_url,
        "extracted": extracted,
        "note": "Review before submitting - this is a draft extraction, not a saved financial record. "
                "Submit the confirmed values through the Reconciliation page to actually create a bank line entry.",
    }
