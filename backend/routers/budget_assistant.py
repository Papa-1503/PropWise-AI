"""
Budget-line setup assistant — a real, conversational AI guide for
setting up a property's monthly budget categories, so staff don't have
to fill in a category/amount form one row at a time. Eighth (and
final, for this round) real feature built on the same agentic
tool-calling pattern established by the other seven assistants.

GET  /api/budget-assistant/status -> real, live count of properties
                                      with NO budget lines at all for
                                      the current calendar month
POST /api/budget-assistant/chat   -> the real conversational loop - 2
                                      real tools
                                      (list_existing_budget_lines,
                                      create_budget_line), the second
                                      of which calls the exact same
                                      real, already-tested logic
                                      already proven in
                                      routers/budgets.py's own
                                      create_budget, including its
                                      real duplicate-detection (one
                                      budget per property+category+
                                      month, enforced by a real unique
                                      index) and real audit logging,
                                      never reimplemented here

SAFETY / SCOPE: identical org-scoping discipline to the other seven
assistants - properties are looked up by name, scoped to the caller's
own org, the same real pattern already established in
routers/onboarding_assistant.py's create_lease tool. Categories are
free text (this app has no closed category enum for budgets - see
routers/budgets.py's own module docstring for why), so the assistant
is instructed to use clear, conventional category names rather than
inventing arbitrary ones.
"""
import os
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends
from anthropic import AsyncAnthropic
from pydantic import BaseModel

from db import budgets_col, properties_col
from auth import require_staff
from routers.budgets import create_budget
from models import BudgetCreate

router = APIRouter(prefix="/api/budget-assistant", tags=["budgets"])

anthropic_client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
MODEL = "claude-haiku-4-5-20251001"
MAX_TOOL_ITERATIONS = 8

SYSTEM_PROMPT = """You are the PropWise AI budget setup assistant. Your job is to help staff quickly set up a property's monthly budget - what they expect to spend, by category, for a given month.

Ask which property and which month (period, as YYYY-MM) they want to set up first, if they haven't said. Common, real categories worth suggesting (not a closed list - staff can use any category name): maintenance, utilities, insurance, landscaping, payroll, marketing, capital improvements. Call list_existing_budget_lines first to see what's already set up for that property/period, so you never suggest a category that's already there (create_budget_line will reject a duplicate anyway, but it's better to catch it yourself first).

Go through categories one at a time - ask what they expect to spend on each, and call create_budget_line once they give a real number. Keep a light running total as you go so they have a sense of the month's total budgeted spend. Ask if they want to add another category after each one, and wrap up when they say they're done."""

TOOLS = [
    {
        "name": "list_existing_budget_lines",
        "description": "Lists the budget lines already set up for a specific property and month.",
        "input_schema": {
            "type": "object",
            "properties": {
                "propertyName": {"type": "string"},
                "period": {"type": "string", "description": "YYYY-MM, e.g. 2026-10"},
            },
            "required": ["propertyName", "period"],
        },
    },
    {
        "name": "create_budget_line",
        "description": "Creates a new budget line (one category's expected spend) for a property and month.",
        "input_schema": {
            "type": "object",
            "properties": {
                "propertyName": {"type": "string"},
                "period": {"type": "string", "description": "YYYY-MM, e.g. 2026-10"},
                "category": {"type": "string"},
                "budgetedAmount": {"type": "number"},
            },
            "required": ["propertyName", "period", "category", "budgetedAmount"],
        },
        "cache_control": {"type": "ephemeral"},
    },
]


class BudgetChatMessage(BaseModel):
    role: str
    content: str


class BudgetChatRequest(BaseModel):
    message: str
    history: list[BudgetChatMessage] = []


async def _current_period() -> str:
    now = datetime.now(timezone.utc)
    return f"{now.year:04d}-{now.month:02d}"


async def _get_unbudgeted_property_count(org_id: str) -> int:
    period = await _current_period()
    properties = await properties_col.find({"orgId": org_id}, {"_id": 1}).to_list(length=500)
    count = 0
    for prop in properties:
        has_budget = await budgets_col.find_one({"propertyId": str(prop["_id"]), "period": period, "orgId": org_id})
        if not has_budget:
            count += 1
    return count


@router.get("/status")
async def budget_assistant_status(user: dict = Depends(require_staff)):
    return {"unbudgetedPropertyCount": await _get_unbudgeted_property_count(user["orgId"]), "currentPeriod": await _current_period()}


async def _find_property_by_name(name: str, org_id: str) -> dict | None:
    return await properties_col.find_one({"name": name, "orgId": org_id})


async def _execute_tool(tool_name: str, tool_input: dict, org_id: str, user: dict) -> dict:
    if tool_name == "list_existing_budget_lines":
        prop = await _find_property_by_name(tool_input.get("propertyName", ""), org_id)
        if not prop:
            return {"error": f"No property named '{tool_input.get('propertyName')}' found in this organization."}
        lines = await budgets_col.find({"propertyId": str(prop["_id"]), "period": tool_input.get("period", ""), "orgId": org_id}).to_list(length=100)
        return {"lines": [{"category": l["category"], "budgetedAmount": l["budgetedAmount"]} for l in lines]}

    elif tool_name == "create_budget_line":
        prop = await _find_property_by_name(tool_input.get("propertyName", ""), org_id)
        if not prop:
            return {"success": False, "error": f"No property named '{tool_input.get('propertyName')}' found in this organization."}
        try:
            payload = BudgetCreate(
                propertyId=str(prop["_id"]), category=tool_input.get("category", ""),
                period=tool_input.get("period", ""), budgetedAmount=tool_input.get("budgetedAmount", 0),
            )
            fake_user = {"orgId": org_id, "id": user.get("id"), "email": user.get("email", "")}
            result = await create_budget(payload, user=fake_user)
            return {"success": True, "category": payload.category, "budgetedAmount": payload.budgetedAmount}
        except HTTPException as exc:
            return {"success": False, "error": exc.detail}

    return {"error": f"Unknown tool: {tool_name}"}


@router.post("/chat")
async def budget_assistant_chat(payload: BudgetChatRequest, user: dict = Depends(require_staff)):
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
            unbudgeted = await _get_unbudgeted_property_count(org_id)
            return {
                "reply": final_text,
                "history": messages + [{"role": "assistant", "content": final_text}],
                "unbudgetedPropertyCount": unbudgeted,
            }

        messages.append({"role": "assistant", "content": [b.model_dump() for b in response.content]})
        tool_results = []
        for block in tool_use_blocks:
            result = await _execute_tool(block.name, block.input, org_id, user)
            tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": str(result)})
        messages.append({"role": "user", "content": tool_results})

    unbudgeted = await _get_unbudgeted_property_count(org_id)
    return {
        "reply": "I've made some progress but want to check in before continuing — want me to keep going?",
        "history": messages,
        "unbudgetedPropertyCount": unbudgeted,
    }
