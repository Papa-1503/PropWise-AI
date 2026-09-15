"""
Custom roles setup assistant — a real, conversational AI guide for
setting up staff permission roles and assigning them, so a new
organization doesn't have to learn this app's permission model cold.
Seventh real feature built on the same agentic tool-calling pattern
established by the other six assistants.

GET  /api/roles-assistant/status -> real, live count of staff who
                                     don't yet have a custom role
                                     assigned (still on full default
                                     access)
POST /api/roles-assistant/chat   -> the real conversational loop - 3
                                     real tools (list_staff_and_roles,
                                     create_custom_role,
                                     assign_role_to_staff), each
                                     calling the exact same real,
                                     already-tested logic already
                                     proven in routers/custom_roles.py
                                     and routers/staff.py, including
                                     create_custom_role's real audit
                                     logging and assign_role_to_staff's
                                     real role-existence check, never
                                     reimplemented here

SAFETY / SCOPE: identical org-scoping discipline to the other six
assistants. Permission choices are constrained to the exact same real,
closed set already defined in models.py's PERMISSION_CHOICES
(leasing, maintenance, finance, communications, staff_management,
reports) - the assistant can never invent a permission that doesn't
structurally exist in this app.
"""
import os
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends
from anthropic import AsyncAnthropic
from bson import ObjectId
from pydantic import BaseModel

from db import users_col, custom_roles_col
from auth import require_staff
from routers.custom_roles import create_custom_role, assign_custom_role
from models import CustomRoleCreate, StaffCustomRoleAssign, PERMISSION_CHOICES

router = APIRouter(prefix="/api/roles-assistant", tags=["custom-roles"])

anthropic_client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
MODEL = "claude-haiku-4-5-20251001"
MAX_TOOL_ITERATIONS = 6

SYSTEM_PROMPT = f"""You are the PropWise AI roles setup assistant. Your job is to help staff set up permission-scoped roles for their team and assign them, without needing to learn this app's role model cold.

Real, available permission areas (a closed set - never invent others): {", ".join(PERMISSION_CHOICES)}. A staff member with NO custom role assigned has full access everywhere by default - custom roles are an opt-in way to narrow that for specific people (e.g. a leasing agent who should only see leasing and communications, not finance).

Start by calling list_staff_and_roles to see who's on the team and what roles already exist. Help the person think through what real roles make sense for their team (e.g. "Leasing Agent" -> leasing + communications; "Maintenance Tech" -> maintenance only) rather than assuming - ask what roles/job functions they actually have. Once you have a role's name and permission list confirmed, create it, then help assign it to the right staff member(s). Confirm each creation and assignment briefly, and ask if they want to set up another role."""

TOOLS = [
    {
        "name": "list_staff_and_roles",
        "description": "Lists this organization's staff members (with their current role assignment) and all existing custom roles.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "create_custom_role",
        "description": "Creates a new named role with a specific set of permission areas.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "permissions": {"type": "array", "items": {"type": "string", "enum": list(PERMISSION_CHOICES)}},
            },
            "required": ["name", "permissions"],
        },
    },
    {
        "name": "assign_role_to_staff",
        "description": "Assigns a custom role to a staff member, by their user ID and the role's ID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "userId": {"type": "string"},
                "customRoleId": {"type": "string"},
            },
            "required": ["userId", "customRoleId"],
        },
        "cache_control": {"type": "ephemeral"},
    },
]


class RolesChatMessage(BaseModel):
    role: str
    content: str


class RolesChatRequest(BaseModel):
    message: str
    history: list[RolesChatMessage] = []


async def _get_unassigned_staff_count(org_id: str) -> int:
    return await users_col.count_documents({
        "role": "staff", "orgId": org_id,
        "$or": [{"customRoleId": {"$exists": False}}, {"customRoleId": None}],
    })


@router.get("/status")
async def roles_assistant_status(user: dict = Depends(require_staff)):
    return {"unassignedStaffCount": await _get_unassigned_staff_count(user["orgId"])}


async def _execute_tool(tool_name: str, tool_input: dict, org_id: str, user: dict) -> dict:
    if tool_name == "list_staff_and_roles":
        staff_cursor = users_col.find({"role": "staff", "orgId": org_id})
        staff = await staff_cursor.to_list(length=200)
        roles_cursor = custom_roles_col.find({"orgId": org_id}).sort("name", 1)
        roles = await roles_cursor.to_list(length=200)
        return {
            "staff": [
                {"userId": str(s["_id"]), "name": s.get("name"), "email": s.get("email"), "customRoleId": s.get("customRoleId")}
                for s in staff
            ],
            "roles": [{"roleId": str(r["_id"]), "name": r.get("name"), "permissions": r.get("permissions")} for r in roles],
        }

    elif tool_name == "create_custom_role":
        name = tool_input.get("name", "").strip()
        permissions = tool_input.get("permissions", [])
        invalid = [p for p in permissions if p not in PERMISSION_CHOICES]
        if invalid:
            return {"success": False, "error": f"Not real permission areas: {', '.join(invalid)}"}
        if not name:
            return {"success": False, "error": "A role name is required."}
        try:
            payload = CustomRoleCreate(name=name, permissions=permissions)
            fake_user = {"orgId": org_id, "id": user.get("id"), "email": user.get("email", "")}
            result = await create_custom_role(payload, user=fake_user)
            return {"success": True, "roleId": result["id"], "name": name}
        except HTTPException as exc:
            return {"success": False, "error": exc.detail}

    elif tool_name == "assign_role_to_staff":
        user_id = tool_input.get("userId", "")
        custom_role_id = tool_input.get("customRoleId")
        try:
            payload = StaffCustomRoleAssign(customRoleId=custom_role_id)
            fake_user = {"orgId": org_id, "id": user.get("id"), "email": user.get("email", "")}
            result = await assign_custom_role(user_id, payload, user=fake_user)
            return {"success": True, "userId": user_id, "customRoleId": custom_role_id}
        except HTTPException as exc:
            return {"success": False, "error": exc.detail}

    return {"error": f"Unknown tool: {tool_name}"}


@router.post("/chat")
async def roles_assistant_chat(payload: RolesChatRequest, user: dict = Depends(require_staff)):
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
            unassigned = await _get_unassigned_staff_count(org_id)
            return {
                "reply": final_text,
                "history": messages + [{"role": "assistant", "content": final_text}],
                "unassignedStaffCount": unassigned,
            }

        messages.append({"role": "assistant", "content": [b.model_dump() for b in response.content]})
        tool_results = []
        for block in tool_use_blocks:
            result = await _execute_tool(block.name, block.input, org_id, user)
            tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": str(result)})
        messages.append({"role": "user", "content": tool_results})

    unassigned = await _get_unassigned_staff_count(org_id)
    return {
        "reply": "I've made some progress but want to check in before continuing — want me to keep going?",
        "history": messages,
        "unassignedStaffCount": unassigned,
    }
