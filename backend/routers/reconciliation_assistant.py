"""
Reconciliation copilot — a real, conversational AI guide that walks
staff through matching unmatched bank statement lines to recorded
charges, one at a time. Same real agentic pattern established by
routers/onboarding_assistant.py (see that module's own docstring for
the full reasoning behind using Claude's tool-use API here rather than
prompt-only text) - this is the second real feature built on it, reusing
the exact same status-endpoint + chat-endpoint + tool-use-loop shape.

GET  /api/reconciliation-assistant/status -> real, live count of
                                              unmatched bank lines for
                                              this org - drives the
                                              progress indicator and
                                              whether this copilot even
                                              has anything to do
POST /api/reconciliation-assistant/chat   -> the real conversational
                                              loop - 3 tools
                                              (list_unmatched_lines,
                                              get_match_suggestions,
                                              match_bank_line), each
                                              executing the exact same
                                              real logic already proven
                                              in routers/reconciliation.py
                                              (this module calls that
                                              router's own functions
                                              directly rather than
                                              re-implementing the
                                              matching logic a second
                                              time)

SAFETY / SCOPE: identical org-scoping discipline to
onboarding_assistant.py - orgId always comes from the authenticated
staff member's own account, never from Claude or the client. Matching
a bank line to the WRONG charge has real financial-reporting
consequences, so match_bank_line is deliberately never auto-run
without the assistant first calling get_match_suggestions and, per
the system prompt, confirming with the person before matching -
Claude is instructed never to match without an explicit yes, but the
one real, structural (not just instructional) guarantee this code
enforces is that every match still goes through the same real
match_bank_line validation (a real charge in this org, a real bank
line in this org) as the existing manual UI already had.
"""
import os

from fastapi import APIRouter, HTTPException, Depends
from anthropic import AsyncAnthropic
from pydantic import BaseModel

from db import bank_lines_col
from auth import require_staff
from routers.reconciliation import serialize
from routers import reconciliation as reconciliation_router
from models import BankLineMatch

router = APIRouter(prefix="/api/reconciliation-assistant", tags=["reconciliation"])

anthropic_client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
MODEL = "claude-haiku-4-5-20251001"
MAX_TOOL_ITERATIONS = 6

SYSTEM_PROMPT = """You are the PropWise AI reconciliation copilot. Your job is to help staff match unmatched bank statement lines to the recorded charges they actually correspond to, one at a time, conversationally.

Start by calling list_unmatched_bank_lines to see what's outstanding. If there are none, congratulate the person - reconciliation is caught up. Otherwise, pick the first line, call get_match_suggestions for it, and present the real options to the person in plain language (the amount, the date, and what each candidate charge looks like). If there's exactly one very obvious candidate (same amount, a close date), you can suggest it directly and ask for a quick yes/no rather than listing options formally.

NEVER call match_bank_line without the person's explicit confirmation first - always ask before matching, even when a candidate looks obviously right. If there are no good candidates for a line, say so honestly and suggest they check the amount or property, then move to the next line rather than guessing.

After a successful match, briefly confirm it, then move on to the next unmatched line without being asked, until the person wants to stop or every line for this session is handled."""

TOOLS = [
    {
        "name": "list_unmatched_bank_lines",
        "description": "Lists this organization's currently unmatched bank statement lines.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_match_suggestions",
        "description": "Gets candidate charges that might match a specific bank line, by ID.",
        "input_schema": {
            "type": "object",
            "properties": {"lineId": {"type": "string"}},
            "required": ["lineId"],
        },
    },
    {
        "name": "match_bank_line",
        "description": "Matches a bank line to a specific charge. Only call this after the person has explicitly confirmed the match.",
        "input_schema": {
            "type": "object",
            "properties": {"lineId": {"type": "string"}, "chargeId": {"type": "string"}},
            "required": ["lineId", "chargeId"],
        },
        "cache_control": {"type": "ephemeral"},
    },
]


class ReconciliationChatMessage(BaseModel):
    role: str
    content: str


class ReconciliationChatRequest(BaseModel):
    message: str
    history: list[ReconciliationChatMessage] = []


async def _get_unmatched_count(org_id: str) -> int:
    return await bank_lines_col.count_documents({"orgId": org_id, "matchedChargeId": None})


@router.get("/status")
async def reconciliation_assistant_status(user: dict = Depends(require_staff)):
    unmatched = await _get_unmatched_count(user["orgId"])
    return {"unmatchedCount": unmatched}


async def _execute_tool(tool_name: str, tool_input: dict, org_id: str) -> dict:
    """Reuses the exact real logic already proven in
    routers/reconciliation.py - this never reimplements matching or
    suggestion logic a second time, it just calls those same real
    functions directly with orgId always taken from the authenticated
    caller, never from tool_input."""
    if tool_name == "list_unmatched_bank_lines":
        lines = await bank_lines_col.find({"orgId": org_id, "matchedChargeId": None}).sort("date", -1).limit(50).to_list(length=50)
        return {"lines": [serialize(dict(l)) for l in lines]}

    elif tool_name == "get_match_suggestions":
        line_id = tool_input.get("lineId", "")
        try:
            fake_user = {"orgId": org_id}
            result = await reconciliation_router.suggest_matches(line_id, user=fake_user)
            return result
        except HTTPException as exc:
            return {"error": exc.detail}

    elif tool_name == "match_bank_line":
        line_id = tool_input.get("lineId", "")
        charge_id = tool_input.get("chargeId", "")
        try:
            fake_user = {"orgId": org_id}
            result = await reconciliation_router.match_bank_line(line_id, BankLineMatch(chargeId=charge_id), user=fake_user)
            return {"success": True, "matched": result}
        except HTTPException as exc:
            return {"success": False, "error": exc.detail}

    return {"error": f"Unknown tool: {tool_name}"}


@router.post("/chat")
async def reconciliation_assistant_chat(payload: ReconciliationChatRequest, user: dict = Depends(require_staff)):
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise HTTPException(status_code=501, detail="The AI assistant isn't configured yet.")

    org_id = user["orgId"]
    messages = [{"role": m.role, "content": m.content} for m in payload.history]
    messages.append({"role": "user", "content": payload.message})

    for _ in range(MAX_TOOL_ITERATIONS):
        response = await anthropic_client.messages.create(
            model=MODEL, max_tokens=1024,
            system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            tools=TOOLS, messages=messages,
        )

        tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
        if not tool_use_blocks:
            final_text = "".join(b.text for b in response.content if b.type == "text")
            unmatched = await _get_unmatched_count(org_id)
            return {
                "reply": final_text,
                "history": messages + [{"role": "assistant", "content": final_text}],
                "unmatchedCount": unmatched,
            }

        messages.append({"role": "assistant", "content": [b.model_dump() for b in response.content]})
        tool_results = []
        for block in tool_use_blocks:
            result = await _execute_tool(block.name, block.input, org_id)
            tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": str(result)})
        messages.append({"role": "user", "content": tool_results})

    unmatched = await _get_unmatched_count(org_id)
    return {
        "reply": "I've made some progress but want to check in before continuing — want me to keep going?",
        "history": messages,
        "unmatchedCount": unmatched,
    }
