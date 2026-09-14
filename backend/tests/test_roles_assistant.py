"""
Roles setup assistant tests — same real mocking approach as the other
six assistants (real anthropic SDK block types; only Claude's own API
call is mocked). What's under real test: does create_custom_role
actually write a real role document (reused from
routers/custom_roles.py, never reimplemented); does
assign_role_to_staff genuinely update the real staff user's
customRoleId; is org isolation preserved; is an invalid permission
name rejected.
"""
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from anthropic.types import TextBlock, ToolUseBlock
from bson import ObjectId

from tests.conftest import auth_headers


def _text_response(text: str):
    return MagicMock(content=[TextBlock(type="text", text=text)])


def _tool_use_response(name: str, tool_input: dict, tool_id: str = "tool_1"):
    return MagicMock(content=[ToolUseBlock(type="tool_use", id=tool_id, name=name, input=tool_input)])


async def _insert_staff_member(patch_db_with_mock, org_id, name="Alex Tech"):
    doc = {"name": name, "email": f"{name.lower().replace(' ', '.')}@example.com", "role": "staff", "orgId": org_id, "password": "hashed"}
    result = await patch_db_with_mock["users"].insert_one(doc)
    return str(result.inserted_id)


@pytest.mark.asyncio
async def test_status_reflects_real_unassigned_staff_count(client, org_a, patch_db_with_mock):
    resp = await client.get("/api/roles-assistant/status", headers=auth_headers(org_a))
    assert resp.status_code == 200
    baseline = resp.json()["unassignedStaffCount"]  # org owner itself counts as unassigned staff

    await _insert_staff_member(patch_db_with_mock, org_a["orgId"])
    resp2 = await client.get("/api/roles-assistant/status", headers=auth_headers(org_a))
    assert resp2.json()["unassignedStaffCount"] == baseline + 1


@pytest.mark.asyncio
async def test_chat_creates_real_custom_role_via_tool_call(client, org_a, patch_db_with_mock):
    tool_call = _tool_use_response("create_custom_role", {"name": "Leasing Agent", "permissions": ["leasing", "communications"]})
    final_reply = _text_response("Created the Leasing Agent role with leasing and communications access.")

    with patch("routers.roles_assistant.anthropic_client.messages.create", new_callable=AsyncMock) as mock_create:
        mock_create.side_effect = [tool_call, final_reply]
        resp = await client.post(
            "/api/roles-assistant/chat",
            json={"message": "Create a Leasing Agent role with leasing and communications access.", "history": []},
            headers=auth_headers(org_a),
        )

    assert resp.status_code == 200, resp.text
    assert "Leasing Agent" in resp.json()["reply"]

    roles = await patch_db_with_mock["custom_roles"].find({"orgId": org_a["orgId"]}).to_list(length=10)
    assert len(roles) == 1
    assert roles[0]["name"] == "Leasing Agent"
    assert set(roles[0]["permissions"]) == {"leasing", "communications"}


@pytest.mark.asyncio
async def test_chat_rejects_invalid_permission_name(client, org_a, patch_db_with_mock):
    tool_call = _tool_use_response("create_custom_role", {"name": "Bad Role", "permissions": ["not-a-real-permission"]})
    final_reply = _text_response("Let me fix that permission and try again.")

    with patch("routers.roles_assistant.anthropic_client.messages.create", new_callable=AsyncMock) as mock_create:
        mock_create.side_effect = [tool_call, final_reply]
        await client.post(
            "/api/roles-assistant/chat",
            json={"message": "Create Bad Role.", "history": []},
            headers=auth_headers(org_a),
        )

    roles = await patch_db_with_mock["custom_roles"].find({"orgId": org_a["orgId"]}).to_list(length=10)
    assert roles == []


@pytest.mark.asyncio
async def test_chat_assigns_real_role_to_real_staff_member(client, org_a, patch_db_with_mock):
    staff_id = await _insert_staff_member(patch_db_with_mock, org_a["orgId"])
    role_result = await patch_db_with_mock["custom_roles"].insert_one({
        "name": "Maintenance Tech", "permissions": ["maintenance"], "orgId": org_a["orgId"],
    })
    role_id = str(role_result.inserted_id)

    tool_call = _tool_use_response("assign_role_to_staff", {"userId": staff_id, "customRoleId": role_id})
    final_reply = _text_response("Assigned Alex Tech to the Maintenance Tech role.")

    with patch("routers.roles_assistant.anthropic_client.messages.create", new_callable=AsyncMock) as mock_create:
        mock_create.side_effect = [tool_call, final_reply]
        resp = await client.post(
            "/api/roles-assistant/chat",
            json={"message": "Assign Alex to Maintenance Tech.", "history": []},
            headers=auth_headers(org_a),
        )

    assert resp.status_code == 200, resp.text

    staff = await patch_db_with_mock["users"].find_one({"_id": ObjectId(staff_id)})
    assert staff["customRoleId"] == role_id


@pytest.mark.asyncio
async def test_chat_never_assigns_roles_across_organizations(client, org_a, org_b, patch_db_with_mock):
    org_b_staff_id = await _insert_staff_member(patch_db_with_mock, org_b["orgId"], name="Org B Person")
    org_b_role_result = await patch_db_with_mock["custom_roles"].insert_one({
        "name": "Org B Role", "permissions": ["reports"], "orgId": org_b["orgId"],
    })
    org_b_role_id = str(org_b_role_result.inserted_id)

    tool_call = _tool_use_response("assign_role_to_staff", {"userId": org_b_staff_id, "customRoleId": org_b_role_id})
    final_reply = _text_response("I couldn't find that staff member or role.")

    with patch("routers.roles_assistant.anthropic_client.messages.create", new_callable=AsyncMock) as mock_create:
        mock_create.side_effect = [tool_call, final_reply]
        await client.post(
            "/api/roles-assistant/chat",
            json={"message": "Assign it.", "history": []},
            headers=auth_headers(org_a),
        )

    staff = await patch_db_with_mock["users"].find_one({"_id": ObjectId(org_b_staff_id)})
    assert staff.get("customRoleId") is None


@pytest.mark.asyncio
async def test_chat_rejects_unauthenticated_requests(client):
    resp = await client.post("/api/roles-assistant/chat", json={"message": "hi", "history": []})
    assert resp.status_code == 401
