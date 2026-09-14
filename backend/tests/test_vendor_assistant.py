"""
Vendor onboarding assistant tests — same real mocking approach as the
other two assistants (real anthropic SDK block types). What's under
real test: does a create_vendor tool call actually write a real,
correctly-shaped vendor into the database; is org isolation preserved;
does validation (invalid category, missing contact method) reject the
tool call with an honest error rather than silently creating a broken
record.
"""
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from anthropic.types import TextBlock, ToolUseBlock

from tests.conftest import auth_headers


def _text_response(text: str):
    return MagicMock(content=[TextBlock(type="text", text=text)])


def _tool_use_response(name: str, tool_input: dict, tool_id: str = "tool_1"):
    return MagicMock(content=[ToolUseBlock(type="tool_use", id=tool_id, name=name, input=tool_input)])


@pytest.mark.asyncio
async def test_status_reflects_real_vendor_count(client, org_a, patch_db_with_mock):
    resp = await client.get("/api/vendor-assistant/status", headers=auth_headers(org_a))
    assert resp.status_code == 200
    assert resp.json()["vendorCount"] == 0

    await patch_db_with_mock["vendors"].insert_one({
        "name": "Acme Plumbing", "category": "plumbing", "orgId": org_a["orgId"], "active": True,
    })
    resp2 = await client.get("/api/vendor-assistant/status", headers=auth_headers(org_a))
    assert resp2.json()["vendorCount"] == 1


@pytest.mark.asyncio
async def test_chat_creates_real_vendor_via_tool_call(client, org_a, patch_db_with_mock):
    tool_call = _tool_use_response("create_vendor", {
        "name": "Acme Plumbing", "category": "plumbing", "phone": "612-555-0100", "baseCost": 150,
    })
    final_reply = _text_response("Added Acme Plumbing! Want to add another vendor?")

    with patch("routers.vendor_assistant.anthropic_client.messages.create", new_callable=AsyncMock) as mock_create:
        mock_create.side_effect = [tool_call, final_reply]
        resp = await client.post(
            "/api/vendor-assistant/chat",
            json={"message": "Add Acme Plumbing, a plumber, phone 612-555-0100, usually costs about $150.", "history": []},
            headers=auth_headers(org_a),
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "Acme Plumbing" in data["reply"]
    assert data["vendorCount"] == 1

    vendors = await patch_db_with_mock["vendors"].find({"orgId": org_a["orgId"]}).to_list(length=10)
    assert len(vendors) == 1
    assert vendors[0]["name"] == "Acme Plumbing"
    assert vendors[0]["category"] == "plumbing"
    assert vendors[0]["phone"] == "612-555-0100"
    assert vendors[0]["baseCost"] == 150
    assert vendors[0]["active"] is True


@pytest.mark.asyncio
async def test_chat_rejects_vendor_with_no_contact_method(client, org_a, patch_db_with_mock):
    tool_call = _tool_use_response("create_vendor", {"name": "No Contact Co", "category": "general"})
    final_reply = _text_response("I need a phone number or email to add that vendor — what's the best way to reach them?")

    with patch("routers.vendor_assistant.anthropic_client.messages.create", new_callable=AsyncMock) as mock_create:
        mock_create.side_effect = [tool_call, final_reply]
        resp = await client.post(
            "/api/vendor-assistant/chat",
            json={"message": "Add a vendor called No Contact Co, general category.", "history": []},
            headers=auth_headers(org_a),
        )

    assert resp.status_code == 200, resp.text
    assert resp.json()["vendorCount"] == 0
    vendors = await patch_db_with_mock["vendors"].find({"orgId": org_a["orgId"]}).to_list(length=10)
    assert vendors == []


@pytest.mark.asyncio
async def test_chat_rejects_invalid_category(client, org_a, patch_db_with_mock):
    tool_call = _tool_use_response("create_vendor", {"name": "Weird Co", "category": "not-a-real-category", "phone": "612-555-0199"})
    final_reply = _text_response("Let me fix that category and try again.")

    with patch("routers.vendor_assistant.anthropic_client.messages.create", new_callable=AsyncMock) as mock_create:
        mock_create.side_effect = [tool_call, final_reply]
        await client.post(
            "/api/vendor-assistant/chat",
            json={"message": "Add Weird Co.", "history": []},
            headers=auth_headers(org_a),
        )

    vendors = await patch_db_with_mock["vendors"].find({"orgId": org_a["orgId"]}).to_list(length=10)
    assert vendors == []


@pytest.mark.asyncio
async def test_chat_tool_creation_is_scoped_to_callers_own_org(client, org_a, org_b, patch_db_with_mock):
    tool_call = _tool_use_response("create_vendor", {"name": "Org A Vendor", "category": "electrical", "phone": "612-555-0177"})
    final_reply = _text_response("Added!")

    with patch("routers.vendor_assistant.anthropic_client.messages.create", new_callable=AsyncMock) as mock_create:
        mock_create.side_effect = [tool_call, final_reply]
        await client.post(
            "/api/vendor-assistant/chat",
            json={"message": "Add a vendor.", "history": []},
            headers=auth_headers(org_a),
        )

    org_b_vendors = await patch_db_with_mock["vendors"].find({"orgId": org_b["orgId"]}).to_list(length=10)
    assert org_b_vendors == []
    org_a_vendors = await patch_db_with_mock["vendors"].find({"orgId": org_a["orgId"]}).to_list(length=10)
    assert len(org_a_vendors) == 1


@pytest.mark.asyncio
async def test_chat_rejects_unauthenticated_requests(client):
    resp = await client.post("/api/vendor-assistant/chat", json={"message": "hi", "history": []})
    assert resp.status_code == 401
