"""
Vendor onboarding assistant — a real, conversational AI guide for
adding a staff member's first few real vendors (plumbers, electricians,
HVAC contractors, etc.), one at a time. Third real feature built on the
same agentic tool-calling pattern established by
routers/onboarding_assistant.py and routers/reconciliation_assistant.py
(see those modules' own docstrings for the full reasoning behind using
Claude's tool-use API here). Reuses that same real shape: a status
endpoint, a chat endpoint, and a bounded tool-use loop.

GET  /api/vendor-assistant/status -> real, live active vendor count
                                      for this org
POST /api/vendor-assistant/chat   -> the real conversational loop -
                                      one real tool (create_vendor)
                                      that writes directly into
                                      vendors_col, reusing the exact
                                      same field shape and defaults
                                      already established in
                                      routers/vendors.py's own
                                      create_vendor endpoint

SAFETY / SCOPE: identical org-scoping discipline to the other two
assistants - orgId always comes from the authenticated staff member's
own account. Vendor records carry no financial risk the way a
reconciliation match does, so this assistant is deliberately more
autonomous than the reconciliation copilot - it can create a vendor
directly once it has a name, category, and at least one contact method,
without a separate confirmation step, since a mistakenly-added vendor
is trivially correctable (edit or deactivate it) in a way a wrong bank
match is not.
"""
import os
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends
from anthropic import AsyncAnthropic
from pydantic import BaseModel

from db import vendors_col
from auth import require_staff
from routers.vendors import serialize

router = APIRouter(prefix="/api/vendor-assistant", tags=["vendors"])

anthropic_client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
MODEL = "claude-haiku-4-5-20251001"
MAX_TOOL_ITERATIONS = 5

VALID_CATEGORIES = ("plumbing", "electrical", "hvac", "general", "landscaping", "locksmith")

SYSTEM_PROMPT = f"""You are the PropWise AI vendor onboarding assistant. Your job is to help staff quickly add their real, trusted vendors (contractors they already work with) - plumbers, electricians, HVAC techs, and so on - so the app has a real roster to assign maintenance work to.

For each vendor, you need: a name, a category (must be exactly one of: {", ".join(VALID_CATEGORIES)}), and at least one contact method (phone or email). A cost estimate (baseCost) is genuinely helpful but optional - ask for it once, don't push if they don't know it offhand.

Once you have a name, a valid category, and at least one contact method, call create_vendor right away - don't ask for confirmation first, a vendor record is easy to fix later if something's off. If the person gives a category that isn't one of the 6 valid ones, pick the closest real match yourself (e.g. "handyman" -> general) rather than asking them to redo it.

After adding a vendor, briefly confirm it and ask if they want to add another. Keep this fast and light - staff are usually adding a handful of vendors, not doing a big form-filling exercise."""

TOOLS = [
    {
        "name": "create_vendor",
        "description": "Creates a new active vendor record for this organization.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "category": {"type": "string", "enum": list(VALID_CATEGORIES)},
                "phone": {"type": "string"},
                "email": {"type": "string"},
                "baseCost": {"type": "number", "description": "A rough typical job cost estimate, if known"},
            },
            "required": ["name", "category"],
        },
        "cache_control": {"type": "ephemeral"},
    },
]


class VendorChatMessage(BaseModel):
    role: str
    content: str


class VendorChatRequest(BaseModel):
    message: str
    history: list[VendorChatMessage] = []


async def _get_vendor_count(org_id: str) -> int:
    return await vendors_col.count_documents({"orgId": org_id, "active": True})


@router.get("/status")
async def vendor_assistant_status(user: dict = Depends(require_staff)):
    count = await _get_vendor_count(user["orgId"])
    return {"vendorCount": count}


async def _execute_tool(tool_name: str, tool_input: dict, org_id: str) -> dict:
    if tool_name == "create_vendor":
        name = tool_input.get("name", "").strip()
        category = tool_input.get("category", "")
        if not name:
            return {"success": False, "error": "A vendor name is required."}
        if category not in VALID_CATEGORIES:
            return {"success": False, "error": f"category must be one of: {', '.join(VALID_CATEGORIES)}"}
        if not tool_input.get("phone") and not tool_input.get("email"):
            return {"success": False, "error": "At least one contact method (phone or email) is required."}

        doc = {
            "name": name, "category": category,
            "rating": 4.5, "distanceMiles": None, "avgArrivalHours": None,
            "baseCost": tool_input.get("baseCost"), "phone": tool_input.get("phone"),
            "email": tool_input.get("email"), "active": True,
            "insuranceExpiresDate": None, "licenseNumber": None, "licenseExpiresDate": None,
            "orgId": org_id, "createdAt": datetime.now(timezone.utc),
        }
        result = await vendors_col.insert_one(doc)
        doc["_id"] = result.inserted_id
        return {"success": True, "vendor": serialize(dict(doc))}

    return {"success": False, "error": f"Unknown tool: {tool_name}"}


@router.post("/chat")
async def vendor_assistant_chat(payload: VendorChatRequest, user: dict = Depends(require_staff)):
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
            count = await _get_vendor_count(org_id)
            return {
                "reply": final_text,
                "history": messages + [{"role": "assistant", "content": final_text}],
                "vendorCount": count,
            }

        messages.append({"role": "assistant", "content": [b.model_dump() for b in response.content]})
        tool_results = []
        for block in tool_use_blocks:
            result = await _execute_tool(block.name, block.input, org_id)
            tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": str(result)})
        messages.append({"role": "user", "content": tool_results})

    count = await _get_vendor_count(org_id)
    return {
        "reply": "I've made some progress but want to check in before continuing — want me to keep going?",
        "history": messages,
        "vendorCount": count,
    }
