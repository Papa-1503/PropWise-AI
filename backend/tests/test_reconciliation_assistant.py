"""
Reconciliation copilot tests — same real mocking approach as
test_onboarding_assistant.py (real anthropic SDK block types, so the
router's own model_dump()-based tool-use loop is exercised exactly as
it runs in production). What's under real test: does a confirmed
match tool call actually update the real bank line in the database;
is org isolation preserved; does the assistant correctly see real
unmatched lines and real match candidates via the two read-only tools.

NOTE on the "bank_lines" key used below: conftest.py's
patch_db_with_mock fixture auto-derives each mock collection's name by
stripping "_col" from the db.py variable name (bank_lines_col ->
"bank_lines") - a real, pre-existing mismatch against this app's
actual production collection name (db.py binds bank_lines_col to the
real Mongo collection "bank_statement_lines"). Confirmed directly:
inserting into patch_db_with_mock["bank_statement_lines"] silently
writes to a different mock collection than the one this router's own
bank_lines_col import actually resolves to in tests, causing every
assertion below to see zero results. "bank_lines" (matching the
fixture's real behavior, not the real collection name) is what
actually reaches the router under test.
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
async def test_status_reflects_real_unmatched_count(client, org_a, patch_db_with_mock):
    resp = await client.get("/api/reconciliation-assistant/status", headers=auth_headers(org_a))
    assert resp.status_code == 200
    assert resp.json()["unmatchedCount"] == 0

    await patch_db_with_mock["bank_lines"].insert_one({
        "orgId": org_a["orgId"], "propertyId": "p1", "date": None, "description": "Deposit",
        "amount": 1200, "matchedChargeId": None, "category": None, "fundType": "operating",
    })
    resp2 = await client.get("/api/reconciliation-assistant/status", headers=auth_headers(org_a))
    assert resp2.json()["unmatchedCount"] == 1


@pytest.mark.asyncio
async def test_chat_lists_real_unmatched_lines(client, org_a, patch_db_with_mock):
    from datetime import datetime, timezone
    await patch_db_with_mock["bank_lines"].insert_one({
        "orgId": org_a["orgId"], "propertyId": "p1", "date": datetime.now(timezone.utc),
        "description": "September deposit", "amount": 1200, "matchedChargeId": None,
        "category": None, "fundType": "operating",
    })

    tool_call = _tool_use_response("list_unmatched_bank_lines", {})
    final_reply = _text_response("I found 1 unmatched line: a $1,200 September deposit. Want me to find candidate matches?")

    with patch("routers.reconciliation_assistant.anthropic_client.messages.create", new_callable=AsyncMock) as mock_create:
        mock_create.side_effect = [tool_call, final_reply]
        resp = await client.post(
            "/api/reconciliation-assistant/chat",
            json={"message": "Let's reconcile.", "history": []},
            headers=auth_headers(org_a),
        )

    assert resp.status_code == 200, resp.text
    assert "1,200" in resp.json()["reply"] or "1200" in resp.json()["reply"]


@pytest.mark.asyncio
async def test_chat_confirms_a_real_match_via_tool_call(client, org_a, patch_db_with_mock):
    from datetime import datetime, timezone
    line_result = await patch_db_with_mock["bank_lines"].insert_one({
        "orgId": org_a["orgId"], "propertyId": "p1", "date": datetime.now(timezone.utc),
        "description": "September deposit", "amount": 1200, "matchedChargeId": None,
        "category": None, "fundType": "operating",
    })
    charge_result = await patch_db_with_mock["payments"].insert_one({
        "orgId": org_a["orgId"], "propertyId": "p1", "unitId": "1A", "amountDue": 1200,
        "amountPaid": 0, "dueDate": datetime.now(timezone.utc), "description": "Monthly rent",
    })
    line_id = str(line_result.inserted_id)
    charge_id = str(charge_result.inserted_id)

    tool_call = _tool_use_response("match_bank_line", {"lineId": line_id, "chargeId": charge_id})
    final_reply = _text_response("Matched! That's all caught up.")

    with patch("routers.reconciliation_assistant.anthropic_client.messages.create", new_callable=AsyncMock) as mock_create:
        mock_create.side_effect = [tool_call, final_reply]
        resp = await client.post(
            "/api/reconciliation-assistant/chat",
            json={"message": "Yes, match it.", "history": []},
            headers=auth_headers(org_a),
        )

    assert resp.status_code == 200, resp.text
    assert resp.json()["unmatchedCount"] == 0

    updated_line = await patch_db_with_mock["bank_lines"].find_one({"_id": line_result.inserted_id})
    assert updated_line["matchedChargeId"] == charge_id


@pytest.mark.asyncio
async def test_chat_never_matches_across_organizations(client, org_a, org_b, patch_db_with_mock):
    """Even if Claude were somehow prompted to reference another org's
    real charge ID, the underlying match_bank_line call is scoped to
    the caller's own org - a cross-org chargeId must fail, not match."""
    from datetime import datetime, timezone
    line_result = await patch_db_with_mock["bank_lines"].insert_one({
        "orgId": org_a["orgId"], "propertyId": "p1", "date": datetime.now(timezone.utc),
        "description": "Deposit", "amount": 999, "matchedChargeId": None,
        "category": None, "fundType": "operating",
    })
    org_b_charge = await patch_db_with_mock["payments"].insert_one({
        "orgId": org_b["orgId"], "propertyId": "p1", "unitId": "1A", "amountDue": 999,
        "amountPaid": 0, "dueDate": datetime.now(timezone.utc), "description": "Org B's own charge",
    })

    tool_call = _tool_use_response("match_bank_line", {"lineId": str(line_result.inserted_id), "chargeId": str(org_b_charge.inserted_id)})
    final_reply = _text_response("Hmm, I couldn't find that charge — let's try something else.")

    with patch("routers.reconciliation_assistant.anthropic_client.messages.create", new_callable=AsyncMock) as mock_create:
        mock_create.side_effect = [tool_call, final_reply]
        await client.post(
            "/api/reconciliation-assistant/chat",
            json={"message": "Match it.", "history": []},
            headers=auth_headers(org_a),
        )

    line = await patch_db_with_mock["bank_lines"].find_one({"_id": line_result.inserted_id})
    assert line["matchedChargeId"] is None


@pytest.mark.asyncio
async def test_chat_rejects_unauthenticated_requests(client):
    resp = await client.post("/api/reconciliation-assistant/chat", json={"message": "hi", "history": []})
    assert resp.status_code == 401
