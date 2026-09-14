"""
Inspection assistant — a real, conversational AI guide that lets an
inspector describe what they find room by room, in natural language,
and has the assistant mark the matching checklist item pass/flag/fail
in real time - instead of tapping through a full checklist UI on a
phone while walking a property. Fifth real feature built on the same
agentic tool-calling pattern established by the other four assistants.

GET  /api/inspection-assistant/status -> real, live count of this
                                          org's inspections that still
                                          have pending items
POST /api/inspection-assistant/chat   -> the real conversational loop -
                                          3 real tools
                                          (list_open_inspections,
                                          get_inspection_items,
                                          mark_item), the last of which
                                          calls the exact same real,
                                          already-tested logic already
                                          proven in
                                          routers/inspections.py's
                                          update_inspection_item -
                                          including its real behavior
                                          of auto-generating a
                                          maintenance ticket the moment
                                          an item is flagged or failed,
                                          inherited here for free,
                                          never reimplemented

SAFETY / SCOPE: identical org-scoping discipline to the other four
assistants. Matching a spoken description ("kitchen faucet is
leaking") to the correct checklist item is exactly the kind of fuzzy,
natural-language matching an LLM is well-suited to - the real,
structural guarantee this code enforces is narrower and more
important: mark_item can only ever update an item that already exists
on a real inspection belonging to the caller's own org (the same
existence and ownership check update_inspection_item itself already
performs), so a mismatched guess fails loudly with a real 404 rather
than silently creating or corrupting a record.
"""
import os

from fastapi import APIRouter, HTTPException, Depends
from anthropic import AsyncAnthropic
from pydantic import BaseModel

from db import inspections_col
from auth import require_staff
from routers.inspections import update_inspection_item
from models import ItemStatusUpdate

router = APIRouter(prefix="/api/inspection-assistant", tags=["inspections"])

anthropic_client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
MODEL = "claude-sonnet-4-6"
MAX_TOOL_ITERATIONS = 8

SYSTEM_PROMPT = """You are the PropWise AI inspection assistant. Your job is to let an inspector describe what they find, room by room, in plain language, while you mark the matching checklist item(s) on their behalf.

Start by calling list_open_inspections to see which inspections still have pending items. If there's more than one, ask which unit/property they're working on right now. Once you know which inspection, call get_inspection_items to see its real checklist (room, description, current status, id) - use this to match what the inspector describes to the right item.

When the inspector describes something ("kitchen's fine", "bathroom faucet is leaking", "living room carpet has a stain"), find the item whose room and description best match what they said, and call mark_item with status=pass for a clean item, or status=flag (minor issue) or status=fail (serious issue, e.g. safety or non-functional) for a problem - include a short, clear description of the actual issue when marking flag or fail, since this becomes the title of a real maintenance ticket. If nothing matches well, ask them to clarify rather than guessing.

Confirm each mark briefly ("Got it, bathroom faucet flagged") and keep moving - inspectors are walking through a real property, not having a long conversation. If marking an item as flag or fail creates a maintenance ticket, you can mention that in passing."""

TOOLS = [
    {
        "name": "list_open_inspections",
        "description": "Lists this organization's inspections that still have at least one pending (unmarked) item.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_inspection_items",
        "description": "Gets the real checklist items (room, description, status, id) for a specific inspection.",
        "input_schema": {
            "type": "object",
            "properties": {"inspectionId": {"type": "string"}},
            "required": ["inspectionId"],
        },
    },
    {
        "name": "mark_item",
        "description": "Marks a specific checklist item's status. Flagging or failing an item automatically creates a real maintenance ticket.",
        "input_schema": {
            "type": "object",
            "properties": {
                "inspectionId": {"type": "string"},
                "itemId": {"type": "string"},
                "status": {"type": "string", "enum": ["pass", "flag", "fail"]},
                "description": {"type": "string", "description": "A short description of the issue - required for flag/fail."},
            },
            "required": ["inspectionId", "itemId", "status"],
        },
    },
]


class InspectionChatMessage(BaseModel):
    role: str
    content: str


class InspectionChatRequest(BaseModel):
    message: str
    history: list[InspectionChatMessage] = []


async def _get_open_count(org_id: str) -> int:
    cursor = inspections_col.find({"orgId": org_id, "items.status": "pending"})
    return len(await cursor.to_list(length=1000))


@router.get("/status")
async def inspection_assistant_status(user: dict = Depends(require_staff)):
    return {"openInspectionCount": await _get_open_count(user["orgId"])}


async def _execute_tool(tool_name: str, tool_input: dict, org_id: str, user: dict) -> dict:
    if tool_name == "list_open_inspections":
        cursor = inspections_col.find({"orgId": org_id, "items.status": "pending"}).sort("createdAt", -1).limit(50)
        inspections = await cursor.to_list(length=50)
        out = []
        for insp in inspections:
            items = insp.get("items", [])
            pending = sum(1 for i in items if i.get("status") == "pending")
            out.append({
                "inspectionId": str(insp["_id"]), "type": insp.get("type"),
                "propertyId": insp.get("propertyId"), "unitId": insp.get("unitId"),
                "totalItems": len(items), "pendingItems": pending,
            })
        return {"inspections": out}

    elif tool_name == "get_inspection_items":
        inspection_id = tool_input.get("inspectionId", "")
        from bson import ObjectId
        if not ObjectId.is_valid(inspection_id):
            return {"error": "Invalid inspection ID."}
        insp = await inspections_col.find_one({"_id": ObjectId(inspection_id), "orgId": org_id})
        if not insp:
            return {"error": "Inspection not found."}
        items = [
            {"id": i.get("id"), "room": i.get("room"), "description": i.get("description"), "status": i.get("status")}
            for i in insp.get("items", [])
        ]
        return {"items": items}

    elif tool_name == "mark_item":
        inspection_id = tool_input.get("inspectionId", "")
        item_id = tool_input.get("itemId", "")
        status = tool_input.get("status", "")
        description = tool_input.get("description")
        try:
            fake_user = {"orgId": org_id}
            payload = ItemStatusUpdate(status=status, description=description)
            result = await update_inspection_item(inspection_id, item_id, payload, user=fake_user)
            updated_item = next((i for i in result.get("items", []) if i.get("id") == item_id), {})
            return {"success": True, "status": status, "ticketCreated": bool(updated_item.get("ticketId"))}
        except HTTPException as exc:
            return {"success": False, "error": exc.detail}

    return {"error": f"Unknown tool: {tool_name}"}


@router.post("/chat")
async def inspection_assistant_chat(payload: InspectionChatRequest, user: dict = Depends(require_staff)):
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
            open_count = await _get_open_count(org_id)
            return {
                "reply": final_text,
                "history": messages + [{"role": "assistant", "content": final_text}],
                "openInspectionCount": open_count,
            }

        messages.append({"role": "assistant", "content": [b.model_dump() for b in response.content]})
        tool_results = []
        for block in tool_use_blocks:
            result = await _execute_tool(block.name, block.input, org_id, user)
            tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": str(result)})
        messages.append({"role": "user", "content": tool_results})

    open_count = await _get_open_count(org_id)
    return {
        "reply": "I've made some progress but want to check in before continuing — want me to keep going?",
        "history": messages,
        "openInspectionCount": open_count,
    }
