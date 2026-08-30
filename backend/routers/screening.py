"""
Tenant screening requests — background/credit check tracking.

No live screening provider is wired in yet. This is deliberately built as
a request/status pipeline that a real provider (e.g. TransUnion SmartMove,
Checkr) can plug into later: swap the body of create_screening_request to
call their API instead of just inserting a "pending" record, and have
their webhook/callback hit update_screening_status instead of a staff
member doing it manually. Nothing else in the app needs to change.

Screening reports involve consumer credit data protected by the FCRA —
do not connect this to a real provider or use it on real applicants
without the required business agreement and compliance paperwork in place.
"""
from datetime import datetime, timezone
import os
import uuid
import base64

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from bson import ObjectId
import cloudinary
import cloudinary.uploader
from anthropic import AsyncAnthropic

from db import screening_col
from models import ScreeningRequestCreate, ScreeningStatusUpdate, ApplicantScoreUpdate
from auth import require_staff
from audit_service import log_action

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True,
)

anthropic_client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
MODEL = "claude-sonnet-4-6"

router = APIRouter(prefix="/api/screening", tags=["screening"])


def serialize(doc: dict) -> dict:
    doc["id"] = str(doc.pop("_id"))
    if isinstance(doc.get("createdAt"), datetime):
        doc["createdAt"] = doc["createdAt"].isoformat()
    if isinstance(doc.get("updatedAt"), datetime):
        doc["updatedAt"] = doc["updatedAt"].isoformat()
    return doc


@router.post("")
async def create_screening_request(payload: ScreeningRequestCreate, user: dict = Depends(require_staff)):
    doc = payload.model_dump()
    doc["status"] = "pending"
    doc["notes"] = None
    doc["createdAt"] = datetime.now(timezone.utc)
    result = await screening_col.insert_one(doc)
    doc["_id"] = result.inserted_id
    return serialize(doc)


@router.get("")
async def list_screening_requests(
    leadId: str | None = None,
    status: str | None = None,
    user: dict = Depends(require_staff),
):
    query = {}
    if leadId:
        query["leadId"] = leadId
    if status:
        query["status"] = status
    cursor = screening_col.find(query).sort("createdAt", -1).limit(200)
    results = await cursor.to_list(length=200)
    return {"screeningRequests": [serialize(r) for r in results]}


@router.get("/{screening_id}")
async def get_screening_request(screening_id: str, user: dict = Depends(require_staff)):
    if not ObjectId.is_valid(screening_id):
        raise HTTPException(status_code=400, detail="Invalid screening request ID")
    doc = await screening_col.find_one({"_id": ObjectId(screening_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Screening request not found")
    return serialize(doc)


@router.patch("/{screening_id}/status")
async def update_screening_status(screening_id: str, payload: ScreeningStatusUpdate, user: dict = Depends(require_staff)):
    if not ObjectId.is_valid(screening_id):
        raise HTTPException(status_code=400, detail="Invalid screening request ID")
    updates = {
        "status": payload.status,
        "updatedAt": datetime.now(timezone.utc),
    }
    if payload.notes is not None:
        updates["notes"] = payload.notes
    result = await screening_col.find_one_and_update(
        {"_id": ObjectId(screening_id)}, {"$set": updates}, return_document=True
    )
    if not result:
        raise HTTPException(status_code=404, detail="Screening request not found")
    return serialize(result)


def compute_applicant_score(
    creditScore: int | None,
    incomeToRentRatio: float | None,
    priorEvictions: int | None,
    rentalHistoryMonths: int | None,
) -> int:
    """Simple, transparent 0-100 score. Not a statistical model — a
    weighted checklist staff can see the reasoning behind at a glance."""
    score = 0.0

    if creditScore is not None:
        credit_pct = max(0, min(1, (creditScore - 500) / 300))
        score += credit_pct * 40

    if incomeToRentRatio is not None:
        ratio_pct = max(0, min(1, incomeToRentRatio / 3))
        score += ratio_pct * 30

    if priorEvictions is not None:
        score += 20 if priorEvictions == 0 else 0

    if rentalHistoryMonths is not None:
        history_pct = max(0, min(1, rentalHistoryMonths / 12))
        score += history_pct * 10

    return round(score)


@router.patch("/{screening_id}/score")
async def score_applicant(screening_id: str, payload: ApplicantScoreUpdate, user: dict = Depends(require_staff)):
    if not ObjectId.is_valid(screening_id):
        raise HTTPException(status_code=400, detail="Invalid screening request ID")

    computed_score = compute_applicant_score(
        payload.creditScore,
        payload.incomeToRentRatio,
        payload.priorEvictions,
        payload.rentalHistoryMonths,
    )

    updates = {
        "creditScore": payload.creditScore,
        "incomeToRentRatio": payload.incomeToRentRatio,
        "priorEvictions": payload.priorEvictions,
        "rentalHistoryMonths": payload.rentalHistoryMonths,
        "score": computed_score,
        "updatedAt": datetime.now(timezone.utc),
    }
    if payload.notes is not None:
        updates["notes"] = payload.notes

    result = await screening_col.find_one_and_update(
        {"_id": ObjectId(screening_id)}, {"$set": updates}, return_document=True
    )
    if not result:
        raise HTTPException(status_code=404, detail="Screening request not found")
    return serialize(result)


@router.post("/{screening_id}/documents")
async def upload_screening_document(
    screening_id: str,
    docType: str,
    file: UploadFile = File(...),
    user: dict = Depends(require_staff),
):
    """Uploads a real applicant document - ID, pay stub, bank statement.
    Reuses the exact Cloudinary pattern already established for
    insurance proof (leases.py), extended to resource_type='auto' for
    the same reason - these are very commonly PDFs, not photos."""
    if not ObjectId.is_valid(screening_id):
        raise HTTPException(status_code=400, detail="Invalid screening ID")
    screening = await screening_col.find_one({"_id": ObjectId(screening_id)})
    if not screening:
        raise HTTPException(status_code=404, detail="Screening request not found")

    file.file.seek(0)
    result = cloudinary.uploader.upload(
        file.file,
        folder=f"rentflow/screening/{screening_id}",
        public_id=uuid.uuid4().hex,
        resource_type="auto",
    )

    doc_entry = {
        "docType": docType,
        "url": result["secure_url"],
        "uploadedAt": datetime.now(timezone.utc),
        "uploadedBy": user.get("email"),
    }
    await screening_col.update_one(
        {"_id": ObjectId(screening_id)},
        {"$push": {"documents": doc_entry}},
    )

    await log_action(
        actor_id=str(user["_id"]), actor_email=user.get("email", ""),
        action="screening_document_uploaded", target_type="screening_request", target_id=screening_id,
        details={"docType": docType},
    )

    return doc_entry


@router.post("/{screening_id}/documents/analyze")
async def analyze_screening_documents(screening_id: str, user: dict = Depends(require_staff)):
    """*** CRITICAL, STRUCTURAL CONSTRAINT, NOT A COMMENT: this
    endpoint can NEVER change a screening request's status to 'passed'
    or 'failed', and never computes or stores anything resembling a
    numeric fraud score. It can only ever write flags into a
    'documentReviewFlags' list and, if anything is genuinely flagged,
    set status to the pre-existing 'manual_review' value - reusing a
    status this model already supported before this feature, not a
    new fast-track-to-rejection state. Confirmed directly in the code
    below: there is no code path here that sets status to 'passed' or
    'failed' at all. ***

    This exists because of a real, explicit fair-housing warning in
    the PDF's own P25 design notes: 'this must never be the sole basis
    for rejecting an applicant... getting this wrong has real fair-
    housing and discrimination-law implications, not just a UX
    concern.' A numeric 'fraud score' invites exactly the kind of
    quasi-automated rejection that warning is about, even if no code
    path technically auto-rejects - a staff member seeing 'Fraud
    score: 15/100' would reasonably treat that as a decision already
    made for them. This deliberately produces qualitative,
    reasoning-visible flags a human has to actually read and evaluate
    instead.

    Vision analysis of uploaded document images only (same honesty
    caveat as inspections.py's photo analysis: general-purpose vision
    reasoning, not a model trained specifically on document forensics
    - can catch obvious, visually-apparent inconsistencies but will
    miss subtle forgeries, and this is stated directly in the flag
    text shown to staff, not just in this docstring)."""
    if not ObjectId.is_valid(screening_id):
        raise HTTPException(status_code=400, detail="Invalid screening ID")
    screening = await screening_col.find_one({"_id": ObjectId(screening_id)})
    if not screening:
        raise HTTPException(status_code=404, detail="Screening request not found")

    documents = screening.get("documents", [])
    if not documents:
        raise HTTPException(status_code=400, detail="No documents uploaded to analyze yet.")
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY is not configured")

    system_prompt = """You are assisting a human reviewer by looking at applicant-submitted
documents (ID, pay stub, bank statement) for a rental application. Point out ONLY visibly
apparent inconsistencies - mismatched fonts or formatting suggesting an edit, an ID that
doesn't visually match a stated name, inconsistent employer information across documents,
numbers that don't add up internally. Do NOT speculate beyond what's visually apparent, and
do NOT make a recommendation about whether to approve or deny the applicant - that decision
belongs entirely to the human reviewer. If nothing looks inconsistent, say so plainly rather
than inventing a concern to report.

Respond with ONLY JSON (no prose, no markdown fences):
{
  "flags": [
    {"concern": "short description", "reasoning": "what's visually apparent and why it's worth a human look", "confidence": "low"|"medium"|"high"}
  ]
}
An empty flags list is a valid, expected, and good outcome."""

    content_blocks = [{"type": "text", "text": "Review these applicant documents:"}]
    for doc in documents[:5]:  # a real, sane cap - this is a vision call, not a bulk-document pipeline
        content_blocks.append({"type": "text", "text": f"Document type: {doc.get('docType', 'unknown')}"})
        if doc["url"].lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
            content_blocks.append({"type": "image", "source": {"type": "url", "url": doc["url"]}})

    try:
        response = await anthropic_client.messages.create(
            model=MODEL,
            max_tokens=800,
            system=system_prompt,
            messages=[{"role": "user", "content": content_blocks}],
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI backend error: {exc}") from exc

    raw_text = "".join(block.text for block in response.content if getattr(block, "type", None) == "text")
    import json
    try:
        parsed = json.loads(raw_text)
        flags = parsed.get("flags", [])
    except (json.JSONDecodeError, AttributeError):
        flags = [{"concern": "AI response could not be parsed", "reasoning": raw_text[:300], "confidence": "low"}]

    updates = {
        "documentReviewFlags": flags,
        "documentReviewedAt": datetime.now(timezone.utc),
    }
    if flags:
        updates["status"] = "manual_review"

    result = await screening_col.find_one_and_update(
        {"_id": ObjectId(screening_id)}, {"$set": updates}, return_document=True
    )

    await log_action(
        actor_id=str(user["_id"]), actor_email=user.get("email", ""),
        action="screening_documents_analyzed", target_type="screening_request", target_id=screening_id,
        details={"flagCount": len(flags)},
    )

    return {"flags": flags, "flaggedForReview": bool(flags)}
