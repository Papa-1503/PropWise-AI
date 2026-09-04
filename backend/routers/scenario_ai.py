"""
Scenario Planner — interactive "what if" AI for staff, e.g. "if I raise
rent 5%, what happens?" or "what if 3 more units go vacant?"

POST /api/ai/scenario

Genuinely different from ai_copilot.py's /copilot: that endpoint hands
Claude a pre-gathered text blob and lets it write an answer directly.
Financial "what if" questions need real arithmetic over potentially
hundreds of units - text-blob context plus free-text generation is
exactly how an LLM would produce a plausible-sounding but wrong dollar
figure. This uses Claude's real tool-use instead: the model decides
WHICH deterministic function in scenario_service.py to call (and with
what inputs) based on the free-text question, that function does the
actual math in plain Python, and Claude only narrates the real result
handed back to it. Same "AI reasoning grounded only in computed
numbers" principle as market_rent.py's comp-based pricing.
"""
import os
import json

from fastapi import APIRouter, HTTPException, Depends
from anthropic import AsyncAnthropic

from models import CopilotRequest, ScenarioResponse
from auth import require_staff
import scenario_service

router = APIRouter(prefix="/api/ai", tags=["ai"])

anthropic_client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
MODEL = "claude-sonnet-4-6"

TOOLS = [
    {
        "name": "portfolio_snapshot",
        "description": "Get the real current state of the portfolio (or one property): unit counts, occupancy, current monthly rent roll, average rent, delinquent balance. Use this for baseline/current-state questions, or to establish a 'before' figure before describing a change.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "simulate_rent_increase",
        "description": "Compute the real effect of raising rent by a percentage on every currently occupied unit in scope. Returns current vs. new total monthly rent roll, dollar/annual increase, and example units. Use this for any question about raising, increasing, or adjusting rent by a percentage.",
        "input_schema": {
            "type": "object",
            "properties": {
                "percent": {"type": "number", "description": "The percent rent increase, e.g. 5 for a 5% increase. Use a negative number for a rent decrease."},
            },
            "required": ["percent"],
        },
    },
    {
        "name": "simulate_occupancy_change",
        "description": "Compute the real revenue impact of a change in the number of occupied units - e.g. more units going vacant (negative unitDelta) or vacancies being filled (positive unitDelta). Use this for questions about vacancy, turnover, or filling/losing units.",
        "input_schema": {
            "type": "object",
            "properties": {
                "unitDelta": {"type": "integer", "description": "Change in occupied unit count. Negative = more vacancies, positive = more units filled."},
            },
            "required": ["unitDelta"],
        },
    },
]

SYSTEM_PROMPT = (
    "You are PropWise AI's portfolio scenario planner for property management staff. "
    "Staff ask hypothetical 'what if' questions about rent changes or occupancy shifts. "
    "You have real tools that compute exact numbers from the live portfolio - ALWAYS use a tool "
    "to get real figures before answering; never estimate or invent a dollar amount yourself. "
    "If a question doesn't map to any tool (e.g. it's not about rent or occupancy), say so plainly "
    "rather than guessing. When you have results, give a direct, specific answer citing the real "
    "numbers - lead with the bottom-line dollar impact, then relevant detail. Keep it concise."
)


async def _execute_tool(name: str, tool_input: dict, property_ids: list[str] | None) -> dict:
    if name == "portfolio_snapshot":
        return await scenario_service.portfolio_snapshot(property_ids)
    if name == "simulate_rent_increase":
        return await scenario_service.simulate_rent_increase(property_ids, tool_input.get("percent", 0))
    if name == "simulate_occupancy_change":
        return await scenario_service.simulate_occupancy_change(property_ids, tool_input.get("unitDelta", 0))
    raise ValueError(f"Unknown tool: {name}")


@router.post("/scenario", response_model=ScenarioResponse)
async def ask_scenario_planner(payload: CopilotRequest, user: dict = Depends(require_staff)):
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY is not configured")

    property_ids = [payload.propertyId] if payload.propertyId else None

    messages = [{"role": t.role, "content": t.content} for t in payload.history]
    messages.append({"role": "user", "content": payload.message})

    sources: list[str] = []
    last_tool_result: dict | None = None

    # Real tool-use loop, capped at 3 rounds so a confused model can't
    # loop indefinitely - every scenario question here should resolve
    # in one tool call, occasionally two (e.g. snapshot then a
    # simulation); 3 is a safety ceiling, not an expected depth.
    for _ in range(3):
        try:
            response = await anthropic_client.messages.create(
                model=MODEL,
                max_tokens=600,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=messages,
            )
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"AI backend error: {exc}") from exc

        if response.stop_reason != "tool_use":
            answer_text = "".join(
                block.text for block in response.content if getattr(block, "type", None) == "text"
            )
            return ScenarioResponse(answer=answer_text, sources=sources, computedData=last_tool_result)

        messages.append({"role": "assistant", "content": response.content})
        tool_results = []
        for block in response.content:
            if getattr(block, "type", None) != "tool_use":
                continue
            try:
                result = await _execute_tool(block.name, block.input, property_ids)
                last_tool_result = result
                sources.append(block.name)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result),
                })
            except Exception as exc:
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": f"Error running this tool: {exc}",
                    "is_error": True,
                })
        messages.append({"role": "user", "content": tool_results})

    raise HTTPException(status_code=502, detail="The scenario planner couldn't resolve this question after several tool calls. Try rephrasing.")
