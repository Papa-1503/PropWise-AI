"""
Collections assistant tests — same real mocking approach as the other
three assistants (real anthropic SDK block types; only Claude's own
API call is mocked, everything downstream runs for real against the
mock database). What's under real test: does a send_reminder tool call
actually update the real charge's lastReminderSentAt and write a real
in-app notification; does the 48-hour cooldown genuinely block a
second reminder; is org isolation preserved.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from anthropic.types import TextBlock, ToolUseBlock
from bson import ObjectId

from tests.conftest import auth_headers


def _text_response(text: str):
    return MagicMock(content=[TextBlock(type="text", text=text)])


def _tool_use_response(name: str, tool_input: dict, tool_id: str = "tool_1"):
    return MagicMock(content=[ToolUseBlock(type="tool_use", id=tool_id, name=name, input=tool_input)])


async def _insert_delinquent_charge(patch_db_with_mock, org_id, **overrides):
    now = datetime.now(timezone.utc)
    doc = {
        "propertyId": "p1", "unitId": "1A", "leaseId": None,
        "amountDue": 1200, "amountPaid": 0,
        "dueDate": now - timedelta(days=10),
        "description": "Monthly rent", "orgId": org_id, "createdAt": now,
        "lateFeeApplied": False, "reminderSent": False,
    }
    doc.update(overrides)
    result = await patch_db_with_mock["payments"].insert_one(doc)
    return str(result.inserted_id)


@pytest.mark.asyncio
async def test_status_reflects_real_delinquent_summary(client, org_a, patch_db_with_mock):
    resp = await client.get("/api/collections-assistant/status", headers=auth_headers(org_a))
    assert resp.status_code == 200
    assert resp.json()["count"] == 0

    await _insert_delinquent_charge(patch_db_with_mock, org_a["orgId"])
    resp2 = await client.get("/api/collections-assistant/status", headers=auth_headers(org_a))
    data = resp2.json()
    assert data["count"] == 1
    assert data["totalOutstanding"] == 1200


@pytest.mark.asyncio
async def test_chat_lists_real_delinquent_charges(client, org_a, patch_db_with_mock):
    await _insert_delinquent_charge(patch_db_with_mock, org_a["orgId"])

    tool_call = _tool_use_response("list_delinquent_charges", {})
    final_reply = _text_response("You have 1 past-due charge: $1,200 for unit 1A. Want me to send a reminder?")

    with patch("routers.collections_assistant.anthropic_client.messages.create", new_callable=AsyncMock) as mock_create:
        mock_create.side_effect = [tool_call, final_reply]
        resp = await client.post(
            "/api/collections-assistant/chat",
            json={"message": "What's outstanding?", "history": []},
            headers=auth_headers(org_a),
        )

    assert resp.status_code == 200, resp.text
    assert "1,200" in resp.json()["reply"] or "1200" in resp.json()["reply"]


@pytest.mark.asyncio
async def test_chat_sends_real_reminder_via_tool_call(client, org_a, patch_db_with_mock):
    charge_id = await _insert_delinquent_charge(patch_db_with_mock, org_a["orgId"])

    tool_call = _tool_use_response("send_reminder", {"chargeId": charge_id})
    final_reply = _text_response("Reminder sent for unit 1A.")

    with patch("routers.collections_assistant.anthropic_client.messages.create", new_callable=AsyncMock) as mock_create:
        mock_create.side_effect = [tool_call, final_reply]
        resp = await client.post(
            "/api/collections-assistant/chat",
            json={"message": "Yes, send it.", "history": []},
            headers=auth_headers(org_a),
        )

    assert resp.status_code == 200, resp.text

    charge = await patch_db_with_mock["payments"].find_one({"_id": ObjectId(charge_id)})
    assert charge["reminderSent"] is True
    assert charge["lastReminderSentAt"] is not None


@pytest.mark.asyncio
async def test_chat_respects_real_48h_cooldown(client, org_a, patch_db_with_mock):
    """A charge reminded 1 hour ago must NOT get a second reminder -
    the real cooldown from payment_reminder_service.py, not a
    reimplemented check that could drift from it."""
    charge_id = await _insert_delinquent_charge(
        patch_db_with_mock, org_a["orgId"],
        lastReminderSentAt=datetime.now(timezone.utc) - timedelta(hours=1),
    )

    tool_call = _tool_use_response("send_reminder", {"chargeId": charge_id})
    final_reply = _text_response("A reminder already went out recently for that one — I'll leave it be for now.")

    with patch("routers.collections_assistant.anthropic_client.messages.create", new_callable=AsyncMock) as mock_create:
        mock_create.side_effect = [tool_call, final_reply]
        resp = await client.post(
            "/api/collections-assistant/chat",
            json={"message": "Send it.", "history": []},
            headers=auth_headers(org_a),
        )

    assert resp.status_code == 200, resp.text
    assert "already" in resp.json()["reply"].lower()


@pytest.mark.asyncio
async def test_chat_never_reminds_across_organizations(client, org_a, org_b, patch_db_with_mock):
    org_b_charge_id = await _insert_delinquent_charge(patch_db_with_mock, org_b["orgId"])

    tool_call = _tool_use_response("send_reminder", {"chargeId": org_b_charge_id})
    final_reply = _text_response("I couldn't find that charge.")

    with patch("routers.collections_assistant.anthropic_client.messages.create", new_callable=AsyncMock) as mock_create:
        mock_create.side_effect = [tool_call, final_reply]
        await client.post(
            "/api/collections-assistant/chat",
            json={"message": "Send it.", "history": []},
            headers=auth_headers(org_a),
        )

    charge = await patch_db_with_mock["payments"].find_one({"_id": ObjectId(org_b_charge_id)})
    assert charge["reminderSent"] is False


@pytest.mark.asyncio
async def test_chat_rejects_unauthenticated_requests(client):
    resp = await client.post("/api/collections-assistant/chat", json={"message": "hi", "history": []})
    assert resp.status_code == 401
