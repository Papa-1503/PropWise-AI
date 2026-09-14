"""
Renewal outreach assistant tests — same real mocking approach as the
other five assistants (real anthropic SDK block types; only Claude's
own API call is mocked). What's under real test: does
offer_renewal_incentive genuinely update the real lease record (reused
from routers/leases.py, never reimplemented here); does the real risk
scoring integrate correctly; is org isolation preserved.
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


async def _insert_expiring_lease(patch_db_with_mock, org_id, days_until_expiration=45, **overrides):
    now = datetime.now(timezone.utc)
    doc = {
        "propertyId": "p1", "unitId": "1A", "residentName": "Jane Doe",
        "residentEmail": "jane@example.com", "orgId": org_id,
        "startDate": now - timedelta(days=320), "endDate": now + timedelta(days=days_until_expiration),
        "rent": 1200, "renewalStatus": "not_sent", "balance": 0, "createdAt": now,
    }
    doc.update(overrides)
    result = await patch_db_with_mock["leases"].insert_one(doc)
    return str(result.inserted_id)


@pytest.mark.asyncio
async def test_status_reflects_real_at_risk_count(client, org_a, patch_db_with_mock):
    resp = await client.get("/api/renewal-assistant/status", headers=auth_headers(org_a))
    assert resp.status_code == 200
    assert resp.json()["atRiskCount"] == 0

    await _insert_expiring_lease(patch_db_with_mock, org_a["orgId"])
    resp2 = await client.get("/api/renewal-assistant/status", headers=auth_headers(org_a))
    assert resp2.json()["atRiskCount"] == 1


@pytest.mark.asyncio
async def test_status_excludes_already_signed_leases(client, org_a, patch_db_with_mock):
    await _insert_expiring_lease(patch_db_with_mock, org_a["orgId"], renewalStatus="signed")
    resp = await client.get("/api/renewal-assistant/status", headers=auth_headers(org_a))
    assert resp.json()["atRiskCount"] == 0


@pytest.mark.asyncio
async def test_chat_lists_real_at_risk_leases_with_scores(client, org_a, patch_db_with_mock):
    await _insert_expiring_lease(patch_db_with_mock, org_a["orgId"])

    tool_call = _tool_use_response("list_at_risk_leases", {})
    final_reply = _text_response("You have 1 lease expiring soon: Jane Doe in unit 1A. Want to reach out?")

    with patch("routers.renewal_assistant.anthropic_client.messages.create", new_callable=AsyncMock) as mock_create:
        mock_create.side_effect = [tool_call, final_reply]
        resp = await client.post(
            "/api/renewal-assistant/chat",
            json={"message": "Who's at risk?", "history": []},
            headers=auth_headers(org_a),
        )

    assert resp.status_code == 200, resp.text
    assert "Jane" in resp.json()["reply"]


@pytest.mark.asyncio
async def test_chat_offers_real_renewal_incentive_via_tool_call(client, org_a, patch_db_with_mock):
    lease_id = await _insert_expiring_lease(patch_db_with_mock, org_a["orgId"])

    tool_call = _tool_use_response("offer_renewal_incentive", {
        "leaseId": lease_id, "description": "$100 off first month if you renew by the 30th",
    })
    final_reply = _text_response("Sent! Jane will see the offer in her portal.")

    with patch("routers.renewal_assistant.anthropic_client.messages.create", new_callable=AsyncMock) as mock_create:
        mock_create.side_effect = [tool_call, final_reply]
        resp = await client.post(
            "/api/renewal-assistant/chat",
            json={"message": "Yes, offer her $100 off first month if she renews by the 30th.", "history": []},
            headers=auth_headers(org_a),
        )

    assert resp.status_code == 200, resp.text

    lease = await patch_db_with_mock["leases"].find_one({"_id": ObjectId(lease_id)})
    assert lease["renewalIncentiveStatus"] == "offered"
    assert "100 off" in lease["renewalIncentiveDescription"]


@pytest.mark.asyncio
async def test_chat_never_offers_incentives_across_organizations(client, org_a, org_b, patch_db_with_mock):
    org_b_lease_id = await _insert_expiring_lease(patch_db_with_mock, org_b["orgId"])

    tool_call = _tool_use_response("offer_renewal_incentive", {"leaseId": org_b_lease_id, "description": "Free parking"})
    final_reply = _text_response("I couldn't find that lease.")

    with patch("routers.renewal_assistant.anthropic_client.messages.create", new_callable=AsyncMock) as mock_create:
        mock_create.side_effect = [tool_call, final_reply]
        await client.post(
            "/api/renewal-assistant/chat",
            json={"message": "Offer it.", "history": []},
            headers=auth_headers(org_a),
        )

    lease = await patch_db_with_mock["leases"].find_one({"_id": ObjectId(org_b_lease_id)})
    assert lease.get("renewalIncentiveStatus") is None


@pytest.mark.asyncio
async def test_chat_rejects_unauthenticated_requests(client):
    resp = await client.post("/api/renewal-assistant/chat", json={"message": "hi", "history": []})
    assert resp.status_code == 401
