"""
Write-with-AI assistant (P18).

POST /api/write-assist/draft  -> drafts an email or SMS from a plain-
                                  English instruction ("tell them their
                                  lease renews soon and offer a tour"),
                                  optionally grounded in a real lease's
                                  actual data if leaseId is given

Genuinely grounded when a lease is provided - the real resident name,
unit, rent, and dates are handed to the model as real context, the
same honesty principle as every other AI feature in this app (never
invent facts the model wasn't given). Without a leaseId, drafts a
generic version and says so in the response, rather than silently
guessing at details it doesn't have.

Always returns a draft for review, never sends anything directly -
the actual send still goes through the existing, separate
communications.py endpoints once staff review and (if needed) edit
the draft. This is a drafting aid, not an autonomous send.
"""
import os

from fastapi import APIRouter, HTTPException, Depends
from anthropic import AsyncAnthropic
from bson import ObjectId
from pydantic import BaseModel

from db import leases_col
from auth import require_staff

router = APIRouter(prefix="/api/write-assist", tags=["write-assist"])

anthropic_client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
MODEL = "claude-sonnet-4-6"


class WriteAssistRequest(BaseModel):
    instruction: str
    channel: str = "email"
    leaseId: str | None = None


@router.post("/draft")
async def draft_message(payload: WriteAssistRequest, user: dict = Depends(require_staff)):
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY is not configured")

    context_text = "No specific resident/lease context provided - write a generic version."
    if payload.leaseId:
        if not ObjectId.is_valid(payload.leaseId):
            raise HTTPException(status_code=400, detail="Invalid lease ID")
        lease = await leases_col.find_one({"_id": ObjectId(payload.leaseId)})
        if not lease:
            raise HTTPException(status_code=404, detail="Lease not found")
        context_text = (
            f"Real resident/lease context - use these actual facts, never invent additional ones: "
            f"Resident: {lease.get('residentName')}. Unit: {lease.get('unitId')}. "
            f"Rent: ${lease.get('rent', 0):,.2f}/month. "
            f"Lease ends: {lease.get('endDate').strftime('%B %d, %Y') if lease.get('endDate') else 'unknown'}."
        )

    channel_note = (
        "Keep this genuinely short and plain - SMS, not email. No subject line."
        if payload.channel == "sms"
        else "Include a short, clear subject line as the first line, then the body."
    )

    system_prompt = (
        "You draft short, professional messages for a property management staff member to "
        "review and send to a resident. Follow the staff member's instruction, using ONLY the "
        "real context given below - never invent a resident name, unit number, dollar amount, "
        "or date not actually provided. If the instruction asks for something the context "
        "doesn't support (e.g. a specific date not given), write around it plainly rather than "
        "making one up. This is a draft for a human to review before sending, not a final "
        f"message - it's fine to be direct and simple. {channel_note}\n\n{context_text}"
    )

    try:
        response = await anthropic_client.messages.create(
            model=MODEL,
            max_tokens=400,
            system=system_prompt,
            messages=[{"role": "user", "content": payload.instruction}],
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI backend error: {exc}") from exc

    draft_text = "".join(
        block.text for block in response.content if getattr(block, "type", None) == "text"
    )

    return {"draft": draft_text, "channel": payload.channel, "groundedInLease": bool(payload.leaseId)}
