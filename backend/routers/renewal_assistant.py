"""
Renewal outreach assistant — a real, conversational AI guide that
walks staff through leases flagged by this app's real renewal-risk
scoring, helping decide who to reach out to and offering (and sending)
a real renewal incentive. Sixth real feature built on the same agentic
tool-calling pattern established by the other five assistants.

GET  /api/renewal-assistant/status -> real, live count of leases
                                       expiring within 90 days that
                                       haven't renewed yet
POST /api/renewal-assistant/chat   -> the real conversational loop -
                                       2 real tools
                                       (list_at_risk_leases,
                                       offer_renewal_incentive), the
                                       second of which calls the exact
                                       same real, already-tested logic
                                       already proven in
                                       routers/leases.py's own
                                       offer_renewal_incentive -
                                       including its real behavior of
                                       immediately notifying the
                                       resident, never reimplemented
                                       here. Risk scoring reuses
                                       renewal_risk_service.py's own
                                       real, explainable weighted
                                       formula (see that module's own
                                       docstring for why it's a
                                       transparent heuristic, not a
                                       trained predictive model) -
                                       the SAME real query window
                                       (leases expiring within 91
                                       days, not yet signed) admin.py's
                                       own automated
                                       _do_renewal_risk_check already
                                       uses, so this assistant's view
                                       of "at risk" never drifts from
                                       what the automated system
                                       already tracks.

SAFETY / SCOPE: identical org-scoping discipline to the other five
assistants. Offering an incentive commits this app to notifying a real
resident and (per offer_renewal_incentive's own real behavior)
represents something staff are prepared to honor - the assistant is
instructed to always confirm with the person before offering, the same
real caution pattern used in the reconciliation copilot for a real
bank match.
"""
import os
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException, Depends
from anthropic import AsyncAnthropic
from bson import ObjectId
from pydantic import BaseModel

from db import leases_col
from auth import require_staff
from routers.leases import offer_renewal_incentive, serialize
from models import RenewalIncentiveOffer
import renewal_risk_service

router = APIRouter(prefix="/api/renewal-assistant", tags=["leases"])

anthropic_client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
MODEL = "claude-sonnet-4-6"
MAX_TOOL_ITERATIONS = 6

SYSTEM_PROMPT = """You are the PropWise AI renewal outreach assistant. Your job is to help staff decide which soon-to-expire leases need real renewal attention, and offer a real incentive where it makes sense.

Start by calling list_at_risk_leases to see who's expiring soon and their real risk scores (low/medium/high, with the real reasons behind each score - payment history, maintenance satisfaction, open tickets). Summarize this for the person, leading with the highest-risk leases first - those are the ones most likely to NOT renew without some real attention.

For a lease the person wants to act on, discuss what incentive might make sense given the real reasons behind their risk score (e.g. if maintenance satisfaction is the issue, a discount alone might not fix the real underlying reason). Always confirm the exact incentive wording and any expiration date with the person BEFORE calling offer_renewal_incentive - never send one without explicit confirmation, since this represents a real commitment to the resident. After offering one, confirm it went out and ask if they want to move to the next lease."""

TOOLS = [
    {
        "name": "list_at_risk_leases",
        "description": "Lists leases expiring within 90 days that haven't renewed yet, each with its real, computed renewal risk score and the reasons behind it.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "offer_renewal_incentive",
        "description": "Offers a specific renewal incentive to a resident and notifies them immediately. Only call this after the person has explicitly confirmed the exact incentive wording.",
        "input_schema": {
            "type": "object",
            "properties": {
                "leaseId": {"type": "string"},
                "description": {"type": "string", "description": "The exact incentive offer, e.g. '$100 off first month' or 'no rent increase for 12 months'"},
                "expiresAt": {"type": "string", "description": "Optional ISO date the offer expires, e.g. 2026-11-01"},
            },
            "required": ["leaseId", "description"],
        },
    },
]


class RenewalChatMessage(BaseModel):
    role: str
    content: str


class RenewalChatRequest(BaseModel):
    message: str
    history: list[RenewalChatMessage] = []


async def _at_risk_query(org_id: str) -> dict:
    now = datetime.now(timezone.utc)
    return {
        "endDate": {"$gte": now, "$lte": now + timedelta(days=91)},
        "renewalStatus": {"$ne": "signed"},
        "orgId": org_id,
    }


async def _get_at_risk_count(org_id: str) -> int:
    return await leases_col.count_documents(await _at_risk_query(org_id))


@router.get("/status")
async def renewal_assistant_status(user: dict = Depends(require_staff)):
    return {"atRiskCount": await _get_at_risk_count(user["orgId"])}


async def _execute_tool(tool_name: str, tool_input: dict, org_id: str, user: dict) -> dict:
    if tool_name == "list_at_risk_leases":
        cursor = leases_col.find(await _at_risk_query(org_id)).sort("endDate", 1).limit(50)
        leases = await cursor.to_list(length=50)
        out = []
        for lease in leases:
            risk = await renewal_risk_service.compute_renewal_risk(lease)
            days_left = renewal_risk_service.days_until(lease.get("endDate"), datetime.now(timezone.utc))
            out.append({
                "leaseId": str(lease["_id"]), "propertyId": lease.get("propertyId"),
                "unitId": lease.get("unitId"), "residentName": lease.get("residentName"),
                "daysUntilExpiration": days_left, "riskLevel": risk.get("riskLevel"),
                "riskScore": risk.get("score"), "riskFactors": risk.get("factors"),
            })
        out.sort(key=lambda x: {"high": 0, "medium": 1, "low": 2}.get(x["riskLevel"], 3))
        return {"leases": out}

    elif tool_name == "offer_renewal_incentive":
        lease_id = tool_input.get("leaseId", "")
        description = tool_input.get("description", "")
        expires_at = tool_input.get("expiresAt")
        if not ObjectId.is_valid(lease_id):
            return {"success": False, "error": "Invalid lease ID."}
        try:
            payload = RenewalIncentiveOffer(description=description, expiresAt=expires_at)
            fake_user = {"orgId": org_id, "id": user.get("id"), "email": user.get("email", "")}
            result = await offer_renewal_incentive(lease_id, payload, user=fake_user)
            return {"success": True, "leaseId": lease_id, "description": description}
        except HTTPException as exc:
            return {"success": False, "error": exc.detail}

    return {"error": f"Unknown tool: {tool_name}"}


@router.post("/chat")
async def renewal_assistant_chat(payload: RenewalChatRequest, user: dict = Depends(require_staff)):
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise HTTPException(status_code=501, detail="The AI assistant isn't configured yet.")

    org_id = user["orgId"]
    messages = [{"role": m.role, "content": m.content} for m in payload.history]
    messages.append({"role": "user", "content": payload.message})

    for _ in range(MAX_TOOL_ITERATIONS):
        response = await anthropic_client.messages.create(
            model=MODEL, max_tokens=1024, system=SYSTEM_PROMPT, tools=TOOLS, messages=messages,
        )

        tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
        if not tool_use_blocks:
            final_text = "".join(b.text for b in response.content if b.type == "text")
            at_risk_count = await _get_at_risk_count(org_id)
            return {
                "reply": final_text,
                "history": messages + [{"role": "assistant", "content": final_text}],
                "atRiskCount": at_risk_count,
            }

        messages.append({"role": "assistant", "content": [b.model_dump() for b in response.content]})
        tool_results = []
        for block in tool_use_blocks:
            result = await _execute_tool(block.name, block.input, org_id, user)
            tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": str(result)})
        messages.append({"role": "user", "content": tool_results})

    at_risk_count = await _get_at_risk_count(org_id)
    return {
        "reply": "I've made some progress but want to check in before continuing — want me to keep going?",
        "history": messages,
        "atRiskCount": at_risk_count,
    }
