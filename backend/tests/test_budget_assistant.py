"""
Budget setup assistant tests — same real mocking approach as the other
seven assistants (real anthropic SDK block types; only Claude's own
API call is mocked). What's under real test: does create_budget_line
actually write a real budget document (reused from
routers/budgets.py's own create_budget, never reimplemented); does the
real duplicate-category constraint get surfaced honestly; is org
isolation preserved via the property-lookup-by-name pattern.
"""
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from anthropic.types import TextBlock, ToolUseBlock

from tests.conftest import auth_headers


def _text_response(text: str):
    return MagicMock(content=[TextBlock(type="text", text=text)])


def _tool_use_response(name: str, tool_input: dict, tool_id: str = "tool_1"):
    return MagicMock(content=[ToolUseBlock(type="tool_use", id=tool_id, name=name, input=tool_input)])


async def _insert_property(patch_db_with_mock, org_id, name="Maple Ridge"):
    result = await patch_db_with_mock["properties"].insert_one({"name": name, "orgId": org_id, "units": []})
    return str(result.inserted_id)


@pytest.mark.asyncio
async def test_status_reflects_real_unbudgeted_property_count(client, org_a, patch_db_with_mock):
    resp = await client.get("/api/budget-assistant/status", headers=auth_headers(org_a))
    assert resp.status_code == 200
    assert resp.json()["unbudgetedPropertyCount"] == 0

    await _insert_property(patch_db_with_mock, org_a["orgId"])
    resp2 = await client.get("/api/budget-assistant/status", headers=auth_headers(org_a))
    assert resp2.json()["unbudgetedPropertyCount"] == 1


@pytest.mark.asyncio
async def test_chat_creates_real_budget_line_via_tool_call(client, org_a, patch_db_with_mock):
    await _insert_property(patch_db_with_mock, org_a["orgId"])

    tool_call = _tool_use_response("create_budget_line", {
        "propertyName": "Maple Ridge", "period": "2026-10", "category": "maintenance", "budgetedAmount": 2000,
    })
    final_reply = _text_response("Added $2,000 for maintenance. Want to add another category?")

    with patch("routers.budget_assistant.anthropic_client.messages.create", new_callable=AsyncMock) as mock_create:
        mock_create.side_effect = [tool_call, final_reply]
        resp = await client.post(
            "/api/budget-assistant/chat",
            json={"message": "Maple Ridge, October, maintenance, $2000.", "history": []},
            headers=auth_headers(org_a),
        )

    assert resp.status_code == 200, resp.text
    assert "2,000" in resp.json()["reply"] or "2000" in resp.json()["reply"]

    lines = await patch_db_with_mock["budgets"].find({"orgId": org_a["orgId"]}).to_list(length=10)
    assert len(lines) == 1
    assert lines[0]["category"] == "maintenance"
    assert lines[0]["budgetedAmount"] == 2000
    assert lines[0]["period"] == "2026-10"


@pytest.mark.asyncio
async def test_chat_rejects_duplicate_category_for_same_month(client, org_a, patch_db_with_mock):
    """The real duplicate-prevention constraint (one budget per
    property+category+month) is enforced by a real unique index -
    ensure_indexes() creates it in production, but the test fixture's
    mock database doesn't call that automatically, so it's created
    explicitly here to exercise the real duplicate-key path
    create_budget itself relies on."""
    await patch_db_with_mock["budgets"].create_index(
        [("propertyId", 1), ("category", 1), ("period", 1)], unique=True
    )
    property_id = await _insert_property(patch_db_with_mock, org_a["orgId"])
    await patch_db_with_mock["budgets"].insert_one({
        "propertyId": property_id, "category": "maintenance", "period": "2026-10",
        "budgetedAmount": 1500, "orgId": org_a["orgId"],
    })

    tool_call = _tool_use_response("create_budget_line", {
        "propertyName": "Maple Ridge", "period": "2026-10", "category": "maintenance", "budgetedAmount": 2000,
    })
    final_reply = _text_response("Looks like maintenance is already set up for October — want to update it instead?")

    with patch("routers.budget_assistant.anthropic_client.messages.create", new_callable=AsyncMock) as mock_create:
        mock_create.side_effect = [tool_call, final_reply]
        await client.post(
            "/api/budget-assistant/chat",
            json={"message": "Add maintenance, $2000.", "history": []},
            headers=auth_headers(org_a),
        )

    lines = await patch_db_with_mock["budgets"].find({"orgId": org_a["orgId"], "propertyId": property_id}).to_list(length=10)
    assert len(lines) == 1
    assert lines[0]["budgetedAmount"] == 1500  # unchanged - the duplicate was rejected


@pytest.mark.asyncio
async def test_chat_lists_real_existing_budget_lines(client, org_a, patch_db_with_mock):
    property_id = await _insert_property(patch_db_with_mock, org_a["orgId"])
    await patch_db_with_mock["budgets"].insert_one({
        "propertyId": property_id, "category": "utilities", "period": "2026-10",
        "budgetedAmount": 800, "orgId": org_a["orgId"],
    })

    tool_call = _tool_use_response("list_existing_budget_lines", {"propertyName": "Maple Ridge", "period": "2026-10"})
    final_reply = _text_response("You already have utilities budgeted at $800 for October. What else would you like to add?")

    with patch("routers.budget_assistant.anthropic_client.messages.create", new_callable=AsyncMock) as mock_create:
        mock_create.side_effect = [tool_call, final_reply]
        resp = await client.post(
            "/api/budget-assistant/chat",
            json={"message": "What's already set up for Maple Ridge in October?", "history": []},
            headers=auth_headers(org_a),
        )

    assert resp.status_code == 200, resp.text
    assert "800" in resp.json()["reply"]


@pytest.mark.asyncio
async def test_chat_never_creates_budget_lines_across_organizations(client, org_a, org_b, patch_db_with_mock):
    await _insert_property(patch_db_with_mock, org_b["orgId"], name="Org B Property")

    tool_call = _tool_use_response("create_budget_line", {
        "propertyName": "Org B Property", "period": "2026-10", "category": "maintenance", "budgetedAmount": 500,
    })
    final_reply = _text_response("I couldn't find a property by that name in your organization.")

    with patch("routers.budget_assistant.anthropic_client.messages.create", new_callable=AsyncMock) as mock_create:
        mock_create.side_effect = [tool_call, final_reply]
        await client.post(
            "/api/budget-assistant/chat",
            json={"message": "Add it.", "history": []},
            headers=auth_headers(org_a),
        )

    lines = await patch_db_with_mock["budgets"].find({"orgId": org_b["orgId"]}).to_list(length=10)
    assert lines == []


@pytest.mark.asyncio
async def test_chat_rejects_unauthenticated_requests(client):
    resp = await client.post("/api/budget-assistant/chat", json={"message": "hi", "history": []})
    assert resp.status_code == 401
