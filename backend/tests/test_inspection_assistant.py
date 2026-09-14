"""
Inspection assistant tests — same real mocking approach as the other
four assistants (real anthropic SDK block types; only Claude's own API
call is mocked). What's under real test: does a mark_item tool call
actually update the real item's status in the database; does flagging
an item genuinely create a real maintenance ticket (inherited for free
from routers/inspections.py's own update_inspection_item, never
reimplemented here); is org isolation preserved.

NOTE on the "tickets" key used below: same real, pre-existing
conftest.py naming mismatch already documented in
test_reconciliation_assistant.py - tickets_col strips to "tickets" in
the auto-patch fixture, not this app's actual production collection
name ("maintenance_tickets", per db.py). "tickets" is what actually
reaches this router in tests.

NOTE on single-item inspections used below: confirmed directly (via an
isolated debug reproduction) that mongomock-motor's find_one_and_update
with the "$" positional operator does not correctly target the array
element that actually matched the filter when an inspection has
MULTIPLE items - it updates whichever item is first in the array
regardless of which id was actually queried for. This is a real
mongomock limitation, not a bug in update_inspection_item itself
(MongoDB Atlas implements the positional operator correctly) - tests
that assert on which specific item changed use a single-item
inspection, so mongomock's limitation can never produce a false pass
or false fail here. test_chat_lists_real_open_inspections, which only
checks list output (not a specific item's post-update state), safely
uses a real two-item inspection.
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


async def _insert_single_item_inspection(patch_db_with_mock, org_id, room="Bathroom", description="Bathroom faucet"):
    doc = {
        "propertyId": "p1", "unitId": "1A", "inspectorName": "Jordan", "type": "move-in",
        "orgId": org_id,
        "items": [{"id": "item-1", "room": room, "description": description, "status": "pending", "role": "maintenance"}],
    }
    result = await patch_db_with_mock["inspections"].insert_one(doc)
    return str(result.inserted_id)


async def _insert_two_item_inspection(patch_db_with_mock, org_id):
    doc = {
        "propertyId": "p1", "unitId": "1A", "inspectorName": "Jordan", "type": "move-in",
        "orgId": org_id,
        "items": [
            {"id": "item-1", "room": "Kitchen", "description": "Kitchen overall condition", "status": "pending", "role": "maintenance"},
            {"id": "item-2", "room": "Bathroom", "description": "Bathroom faucet", "status": "pending", "role": "maintenance"},
        ],
    }
    result = await patch_db_with_mock["inspections"].insert_one(doc)
    return str(result.inserted_id)


@pytest.mark.asyncio
async def test_status_reflects_real_open_inspection_count(client, org_a, patch_db_with_mock):
    resp = await client.get("/api/inspection-assistant/status", headers=auth_headers(org_a))
    assert resp.status_code == 200
    assert resp.json()["openInspectionCount"] == 0

    await _insert_single_item_inspection(patch_db_with_mock, org_a["orgId"])
    resp2 = await client.get("/api/inspection-assistant/status", headers=auth_headers(org_a))
    assert resp2.json()["openInspectionCount"] == 1


@pytest.mark.asyncio
async def test_chat_marks_item_pass_via_tool_call(client, org_a, patch_db_with_mock):
    inspection_id = await _insert_single_item_inspection(patch_db_with_mock, org_a["orgId"], room="Kitchen", description="Kitchen overall condition")

    tool_call = _tool_use_response("mark_item", {"inspectionId": inspection_id, "itemId": "item-1", "status": "pass"})
    final_reply = _text_response("Got it, kitchen marked as pass. What's next?")

    with patch("routers.inspection_assistant.anthropic_client.messages.create", new_callable=AsyncMock) as mock_create:
        mock_create.side_effect = [tool_call, final_reply]
        resp = await client.post(
            "/api/inspection-assistant/chat",
            json={"message": "Kitchen's fine.", "history": []},
            headers=auth_headers(org_a),
        )

    assert resp.status_code == 200, resp.text

    insp = await patch_db_with_mock["inspections"].find_one({"_id": ObjectId(inspection_id)})
    assert insp["items"][0]["status"] == "pass"


@pytest.mark.asyncio
async def test_chat_flag_creates_real_maintenance_ticket(client, org_a, patch_db_with_mock):
    """Real, inherited behavior from update_inspection_item - flagging
    an item must genuinely create a maintenance ticket, not just
    update the item's status."""
    inspection_id = await _insert_single_item_inspection(patch_db_with_mock, org_a["orgId"])

    tool_call = _tool_use_response("mark_item", {
        "inspectionId": inspection_id, "itemId": "item-1", "status": "flag",
        "description": "Bathroom faucet is leaking",
    })
    final_reply = _text_response("Flagged the bathroom faucet — a maintenance ticket has been created.")

    with patch("routers.inspection_assistant.anthropic_client.messages.create", new_callable=AsyncMock) as mock_create:
        mock_create.side_effect = [tool_call, final_reply]
        resp = await client.post(
            "/api/inspection-assistant/chat",
            json={"message": "Bathroom faucet is leaking.", "history": []},
            headers=auth_headers(org_a),
        )

    assert resp.status_code == 200, resp.text

    insp = await patch_db_with_mock["inspections"].find_one({"_id": ObjectId(inspection_id)})
    assert insp["items"][0]["status"] == "flag"
    assert insp["items"][0].get("ticketId")

    tickets = await patch_db_with_mock["tickets"].find({"orgId": org_a["orgId"]}).to_list(length=10)
    assert len(tickets) == 1
    assert "leaking" in tickets[0]["title"].lower()


@pytest.mark.asyncio
async def test_chat_lists_real_open_inspections(client, org_a, patch_db_with_mock):
    await _insert_two_item_inspection(patch_db_with_mock, org_a["orgId"])

    tool_call = _tool_use_response("list_open_inspections", {})
    final_reply = _text_response("You have 1 open inspection: a move-in for unit 1A. Want to work on that one?")

    with patch("routers.inspection_assistant.anthropic_client.messages.create", new_callable=AsyncMock) as mock_create:
        mock_create.side_effect = [tool_call, final_reply]
        resp = await client.post(
            "/api/inspection-assistant/chat",
            json={"message": "What's open?", "history": []},
            headers=auth_headers(org_a),
        )

    assert resp.status_code == 200, resp.text
    assert "1a" in resp.json()["reply"].lower() or "1A" in resp.json()["reply"]


@pytest.mark.asyncio
async def test_chat_never_marks_items_across_organizations(client, org_a, org_b, patch_db_with_mock):
    org_b_inspection_id = await _insert_single_item_inspection(patch_db_with_mock, org_b["orgId"])

    tool_call = _tool_use_response("mark_item", {"inspectionId": org_b_inspection_id, "itemId": "item-1", "status": "pass"})
    final_reply = _text_response("I couldn't find that inspection.")

    with patch("routers.inspection_assistant.anthropic_client.messages.create", new_callable=AsyncMock) as mock_create:
        mock_create.side_effect = [tool_call, final_reply]
        await client.post(
            "/api/inspection-assistant/chat",
            json={"message": "Mark it.", "history": []},
            headers=auth_headers(org_a),
        )

    insp = await patch_db_with_mock["inspections"].find_one({"_id": ObjectId(org_b_inspection_id)})
    assert insp["items"][0]["status"] == "pending"  # unchanged


@pytest.mark.asyncio
async def test_chat_rejects_unauthenticated_requests(client):
    resp = await client.post("/api/inspection-assistant/chat", json={"message": "hi", "history": []})
    assert resp.status_code == 401
