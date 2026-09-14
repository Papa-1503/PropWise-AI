"""
Onboarding assistant — a real, conversational AI guide for a brand-new
organization's first setup steps (first property, first lease, then
billing). Genuinely new pattern for this codebase: every other AI
feature here (ai_copilot.py, scenario_ai.py, etc.) is prompt-only -
Claude reasons and writes text, but never directly changes the
database. This uses Claude's real tool-use (function-calling) API so
the assistant can actually CREATE a property or lease as the person
describes it conversationally, rather than only explaining which
screen to go fill in a form on.

GET  /api/onboarding/status -> real, live setup progress (property
                                count, lease count, billing status) -
                                the frontend uses this to show a
                                progress indicator and to know when
                                setup is genuinely complete
POST /api/onboarding/chat   -> the real conversational loop - takes
                                the user's message plus prior history,
                                runs Claude with 2 real tools
                                (create_property, create_lease),
                                executes any tool calls against this
                                org's real database, and returns the
                                assistant's natural-language reply

SAFETY / SCOPE: every tool call is executed with orgId taken from the
authenticated staff member's own account - NEVER from anything Claude
or the client submits. This mirrors the same never-trust-client-
submitted-scope principle already established throughout this app
(see routers/auth.py's TenantActivate). require_staff gates the whole
router - onboarding setup is a staff action, not a tenant one. The
tool-use loop is capped at MAX_TOOL_ITERATIONS to bound both real cost
and worst-case latency if a conversation somehow triggered a runaway
sequence of tool calls.
"""
import os
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends
from anthropic import AsyncAnthropic
from bson import ObjectId
from pydantic import BaseModel

from db import properties_col, leases_col, organizations_col
from auth import require_staff
from routers.leases import generate_invite_code

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])

anthropic_client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
MODEL = "claude-sonnet-4-6"
MAX_TOOL_ITERATIONS = 5

SYSTEM_PROMPT = """You are the PropWise AI setup assistant. Your job is to warmly and efficiently guide a brand-new property management company through their first setup steps: adding their first property (with at least one unit), then adding their first lease for a resident.

Be conversational and encouraging - this is often someone's first time in the product. Ask for one piece of information at a time rather than overwhelming them with a long form's worth of questions at once. Once you have enough information for a step, use the matching tool to actually create it - don't just describe what you would do.

Real, required info for create_property: a property name, an address, and at least one unit (a unit ID/number, monthly rent, bedrooms, bathrooms).
Real, required info for create_lease: which property/unit it's for, the resident's name, lease start and end dates, and the monthly rent (default to the unit's own rent if the person doesn't specify a different one).

After a lease is successfully created, congratulate them and mention that the next step is subscribing to a plan under Settings > Billing, but don't try to do that yourself - billing has no tool here on purpose."""

TOOLS = [
    {
        "name": "create_property",
        "description": "Creates a new property with one or more units in this organization's real portfolio.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "The property's name"},
                "address": {"type": "string", "description": "The property's street address"},
                "units": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "unitId": {"type": "string"},
                            "rent": {"type": "number"},
                            "bedrooms": {"type": "integer"},
                            "bathrooms": {"type": "number"},
                        },
                        "required": ["unitId", "rent", "bedrooms", "bathrooms"],
                    },
                },
            },
            "required": ["name", "address", "units"],
        },
    },
    {
        "name": "create_lease",
        "description": "Creates a new lease for a resident in an already-created property/unit.",
        "input_schema": {
            "type": "object",
            "properties": {
                "propertyName": {"type": "string", "description": "The exact name of the property this lease is for"},
                "unitId": {"type": "string"},
                "residentName": {"type": "string"},
                "residentEmail": {"type": "string"},
                "startDate": {"type": "string", "description": "ISO date, e.g. 2026-10-01"},
                "endDate": {"type": "string", "description": "ISO date, e.g. 2027-09-30"},
                "rent": {"type": "number"},
            },
            "required": ["propertyName", "unitId", "residentName", "startDate", "endDate", "rent"],
        },
    },
]


class OnboardingChatMessage(BaseModel):
    role: str
    content: str


class OnboardingChatRequest(BaseModel):
    message: str
    history: list[OnboardingChatMessage] = []


async def _get_setup_status(org_id: str) -> dict:
    """Real, live counts - never a separately-stored, staleable
    progress flag. Used by both GET /status and to decide when to
    stop nudging the person toward billing in the system prompt's own
    reasoning (implicitly, via what the assistant can see in tool
    results)."""
    property_count = await properties_col.count_documents({"orgId": org_id})
    lease_count = await leases_col.count_documents({"orgId": org_id})
    query_id = ObjectId(org_id) if ObjectId.is_valid(org_id) else org_id
    org = await organizations_col.find_one({"_id": query_id})
    plan = org.get("plan") if org else None
    return {
        "propertyCount": property_count,
        "leaseCount": lease_count,
        "billingPlan": plan,
        "setupComplete": property_count > 0 and lease_count > 0,
    }


@router.get("/status")
async def onboarding_status(user: dict = Depends(require_staff)):
    return await _get_setup_status(user["orgId"])


async def _execute_tool(tool_name: str, tool_input: dict, org_id: str) -> dict:
    """The real, actual database-writing step - orgId is ALWAYS the
    authenticated caller's own real org, injected here, never read
    from tool_input even though Claude never includes it in the first
    place (it isn't part of either tool's real input_schema above) -
    a defensive, structural guarantee, not just an instruction to the
    model."""
    if tool_name == "create_property":
        units = [
            {
                "unitId": str(u["unitId"]), "status": "vacant",
                "rent": u["rent"], "bedrooms": u["bedrooms"], "bathrooms": u["bathrooms"],
                "readyToList": True,
            }
            for u in tool_input.get("units", [])
        ]
        doc = {
            "name": tool_input["name"], "address": tool_input.get("address", ""),
            "units": units, "orgId": org_id, "createdAt": datetime.now(timezone.utc),
        }
        result = await properties_col.insert_one(doc)
        return {"success": True, "propertyId": str(result.inserted_id), "unitsCreated": len(units)}

    elif tool_name == "create_lease":
        property_doc = await properties_col.find_one({"name": tool_input["propertyName"], "orgId": org_id})
        if not property_doc:
            return {"success": False, "error": f"No property named '{tool_input['propertyName']}' found in this organization yet — create the property first."}

        try:
            start_date = datetime.fromisoformat(tool_input["startDate"]).replace(tzinfo=timezone.utc)
            end_date = datetime.fromisoformat(tool_input["endDate"]).replace(tzinfo=timezone.utc)
        except ValueError:
            return {"success": False, "error": "Dates must be in ISO format, e.g. 2026-10-01."}

        doc = {
            "propertyId": str(property_doc["_id"]), "unitId": tool_input["unitId"],
            "residentName": tool_input["residentName"], "residentEmail": tool_input.get("residentEmail"),
            "residentPhone": None, "startDate": start_date, "endDate": end_date,
            "rent": tool_input["rent"], "renewalStatus": "not_sent", "insuranceRequired": False,
            "depositAmount": 0, "balance": 0, "inviteCode": generate_invite_code(),
            "orgId": org_id, "createdAt": datetime.now(timezone.utc),
        }
        result = await leases_col.insert_one(doc)
        return {"success": True, "leaseId": str(result.inserted_id), "inviteCode": doc["inviteCode"]}

    return {"success": False, "error": f"Unknown tool: {tool_name}"}


@router.post("/chat")
async def onboarding_chat(payload: OnboardingChatRequest, user: dict = Depends(require_staff)):
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
            # Real, final text-only reply - the loop is done.
            final_text = "".join(b.text for b in response.content if b.type == "text")
            status = await _get_setup_status(org_id)
            return {
                "reply": final_text,
                "history": messages + [{"role": "assistant", "content": final_text}],
                "status": status,
            }

        # Claude asked to use one or more tools - execute each for
        # real against this org's own database, then feed the real
        # results back so Claude can continue the conversation.
        messages.append({"role": "assistant", "content": [b.model_dump() for b in response.content]})
        tool_results = []
        for block in tool_use_blocks:
            result = await _execute_tool(block.name, block.input, org_id)
            tool_results.append({
                "type": "tool_result", "tool_use_id": block.id,
                "content": str(result),
            })
        messages.append({"role": "user", "content": tool_results})

    # Safety exit - a real, honest response if MAX_TOOL_ITERATIONS was
    # somehow exhausted, rather than an unbounded loop or a silent 500.
    status = await _get_setup_status(org_id)
    return {
        "reply": "I've made some progress but want to check in before continuing — what would you like to do next?",
        "history": messages,
        "status": status,
    }
