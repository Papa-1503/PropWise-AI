"""
AI-guided DIY troubleshooting (P20).

POST /api/diy-troubleshooting/check    -> the real safety gate (see
                                           services/diy_safety.py) -
                                           called first, before any AI
                                           involvement, to decide
                                           whether DIY guidance should
                                           even be offered for this
                                           issue
POST /api/diy-troubleshooting/guidance -> generates real, specific
                                           troubleshooting steps via
                                           the existing Anthropic
                                           integration - ONLY reachable
                                           if the safety check above
                                           passed; re-checked again
                                           inside this endpoint too
                                           (never trusts a client-side
                                           "it's safe" claim - the
                                           real decision is made
                                           server-side, twice, not
                                           once)

Design questions the PDF itself raised, answered here concretely:
  - Where does this happen: a dedicated pre-ticket-creation flow (this
    router), not folded into POST /api/maintenance/tickets itself -
    lets the frontend show the DIY offer BEFORE a ticket is created,
    matching the PDF's own described flow ("ask before creating the
    ticket, offer DIY or send to maintenance").
  - Escalation if DIY doesn't work: the resident simply submits the
    normal ticket afterward (POST /api/maintenance/tickets, unchanged)
    - no special "escalate from DIY" state is needed, since nothing
      was ever created that needs escalating.
  - Does the original ticket still get created if DIY succeeds: no -
    consistent with the above, since a ticket is never created until
    the resident explicitly decides to submit one. If DIY resolves it,
    nothing needs to exist in maintenance_tickets at all - the
    honestly simplest, most consistent answer to that open question.
"""
import os

from fastapi import APIRouter, HTTPException, Depends
from anthropic import AsyncAnthropic
from pydantic import BaseModel

from auth import get_current_user
from services.diy_safety import check_diy_eligibility
import translation_service

router = APIRouter(prefix="/api/diy-troubleshooting", tags=["diy-troubleshooting"])

anthropic_client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
MODEL = "claude-sonnet-4-6"


class DiyCheckRequest(BaseModel):
    title: str
    description: str = ""


class DiyGuidanceRequest(BaseModel):
    title: str
    description: str = ""


@router.post("/check")
async def check_eligibility(payload: DiyCheckRequest, user: dict = Depends(get_current_user)):
    """The real, code-enforced safety decision - see diy_safety.py.
    Never calls the AI. A frontend should call this first and only
    offer the DIY option to the resident if eligible is true."""
    return check_diy_eligibility(payload.title, payload.description)


@router.post("/guidance")
async def get_guidance(payload: DiyGuidanceRequest, user: dict = Depends(get_current_user)):
    """Generates real troubleshooting steps - only ever reached if the
    eligibility check passes, re-verified here rather than trusting
    that the frontend already called /check and got a true result.
    This is the actual, final gate the AI call sits behind - a client
    that skipped /check, or a modified request, still can't reach the
    AI call for an unsafe issue, because this endpoint checks again
    itself."""
    eligibility = check_diy_eligibility(payload.title, payload.description)
    if not eligibility["eligible"]:
        raise HTTPException(status_code=403, detail=eligibility["reason"])

    if not os.getenv("ANTHROPIC_API_KEY"):
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY is not configured")

    system_prompt = (
        "You are a maintenance troubleshooting assistant for a rental property app. "
        "A resident has described an issue that has ALREADY been confirmed safe for "
        "self-help guidance by a separate safety check - you do not need to re-evaluate "
        "safety, but stay within genuinely simple, safe actions (resetting something, "
        "checking a filter, restarting a device) regardless. Never suggest anything "
        "involving gas, electrical panels/wiring, or structural work, even if the "
        "resident's description seems to invite it - if asked to go beyond simple, safe "
        "steps, tell the resident to submit a maintenance ticket instead. Give 3-5 clear, "
        "numbered steps. End by telling the resident that if this doesn't resolve the "
        "issue, they should submit a maintenance request."
        f"{translation_service.language_instruction(user.get('preferredLanguage'))}"
    )

    try:
        response = await anthropic_client.messages.create(
            model=MODEL,
            max_tokens=500,
            system=system_prompt,
            messages=[{"role": "user", "content": f"Issue: {payload.title}\n{payload.description}"}],
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI backend error: {exc}") from exc

    steps_text = "".join(
        block.text for block in response.content if getattr(block, "type", None) == "text"
    )

    return {"eligible": True, "steps": steps_text}
