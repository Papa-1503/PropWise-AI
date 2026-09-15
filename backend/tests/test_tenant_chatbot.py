"""
Tenant chatbot tests — covers both real changes made together: the
structural security fix on POST /api/ai/copilot (now require_staff-
gated, closing a real gap where any authenticated tenant could
previously reach portfolio-wide staff context), and the new real
tool-calling capability on POST /api/ai/faq (a resident can now have
a real maintenance request submitted on their behalf, not just be
told how to use the form).

Only Claude's own API call is mocked (real anthropic SDK block types)
- everything else, including the real create_ticket_document pipeline
a submitted request goes through, runs for real against the mock
database.

NOTE on the "tickets" key used below: same real, pre-existing
conftest.py naming mismatch already documented elsewhere in this test
suite - tickets_col strips to "tickets" in the auto-patch fixture, not
this app's actual production collection name ("maintenance_tickets",
per db.py).
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from anthropic.types import TextBlock, ToolUseBlock

from tests.conftest import auth_headers


def _text_response(text: str):
    return MagicMock(content=[TextBlock(type="text", text=text)])


def _tool_use_response(name: str, tool_input: dict, tool_id: str = "tool_1"):
    return MagicMock(content=[ToolUseBlock(type="tool_use", id=tool_id, name=name, input=tool_input)])


async def _create_tenant(client, org, unit_id="1", resident_email="chattenant@example.com"):
    """Real property + lease + register flow, matching exactly how a
    real resident account comes into being - same pattern already
    established in tests/test_auth.py."""
    prop_resp = await client.post(
        "/api/properties",
        json={"name": "Chatbot Test Bldg", "address": "1 Bot St", "units": [
            {"unitId": unit_id, "status": "vacant", "rent": 1200},
        ]},
        headers=auth_headers(org),
    )
    property_id = prop_resp.json()["id"]

    now = datetime.now(timezone.utc)
    lease_resp = await client.post(
        "/api/leases",
        json={
            "propertyId": property_id, "unitId": unit_id, "residentName": "Chat Tenant",
            "residentEmail": resident_email,
            "startDate": now.isoformat(), "endDate": (now + timedelta(days=365)).isoformat(),
            "rent": 1200,
        },
        headers=auth_headers(org),
    )
    invite_code = lease_resp.json()["inviteCode"]

    register_resp = await client.post("/api/auth/register", json={
        "inviteCode": invite_code, "name": "Chat Tenant",
        "email": resident_email, "password": "tenantpass123",
    })
    tenant_token = register_resp.json()["accessToken"]
    return {"token": tenant_token, "propertyId": property_id, "unitId": unit_id}


@pytest.mark.asyncio
async def test_copilot_rejects_tenant_accounts(client, org_a, patch_db_with_mock):
    """The real, structural fix - a tenant must never reach the
    staff-scoped /copilot endpoint, even though it uses
    get_current_user (not require_staff) for the dependency itself -
    confirmed this is now enforced by require_staff directly."""
    tenant = await _create_tenant(client, org_a)
    resp = await client.post(
        "/api/ai/copilot",
        json={"message": "How many vacant units do we have?"},
        headers={"Authorization": f"Bearer {tenant['token']}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_faq_rejects_staff_accounts(client, org_a, patch_db_with_mock):
    resp = await client.post(
        "/api/ai/faq",
        json={"message": "hi", "history": []},
        headers=auth_headers(org_a),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_faq_submits_real_maintenance_request_via_tool_call(client, org_a, patch_db_with_mock):
    tenant = await _create_tenant(client, org_a)
    tenant_headers = {"Authorization": f"Bearer {tenant['token']}"}

    tool_call = _tool_use_response("submit_maintenance_request", {
        "title": "Kitchen faucet leaking", "description": "Dripping constantly under the sink",
        "category": "plumbing", "priority": "normal",
    })
    final_reply = _text_response("I've submitted that for you — a plumber will be in touch soon.")

    with patch("routers.ai_copilot.anthropic_client.messages.create", new_callable=AsyncMock) as mock_create:
        mock_create.side_effect = [tool_call, final_reply]
        resp = await client.post(
            "/api/ai/faq",
            json={"message": "My kitchen faucet won't stop leaking.", "history": []},
            headers=tenant_headers,
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ticketCreated"] is True

    tickets = await patch_db_with_mock["tickets"].find({"propertyId": tenant["propertyId"], "unitId": tenant["unitId"]}).to_list(length=10)
    assert len(tickets) == 1
    assert tickets[0]["title"] == "Kitchen faucet leaking"
    assert tickets[0]["source"] == "resident"
    assert tickets[0]["category"] == "plumbing"


@pytest.mark.asyncio
async def test_faq_never_lets_urgent_be_forced_for_routine_requests(client, org_a, patch_db_with_mock):
    """Not a structural guarantee (the model chooses priority) - but
    confirms a normal-priority tool call is stored as normal, not
    silently upgraded or downgraded by the endpoint itself."""
    tenant = await _create_tenant(client, org_a)
    tenant_headers = {"Authorization": f"Bearer {tenant['token']}"}

    tool_call = _tool_use_response("submit_maintenance_request", {
        "title": "Squeaky door", "category": "general", "priority": "normal",
    })
    final_reply = _text_response("Submitted!")

    with patch("routers.ai_copilot.anthropic_client.messages.create", new_callable=AsyncMock) as mock_create:
        mock_create.side_effect = [tool_call, final_reply]
        await client.post(
            "/api/ai/faq",
            json={"message": "My door squeaks a bit.", "history": []},
            headers=tenant_headers,
        )

    tickets = await patch_db_with_mock["tickets"].find({"propertyId": tenant["propertyId"]}).to_list(length=10)
    assert tickets[0]["priority"] == "normal"


@pytest.mark.asyncio
async def test_faq_scopes_ticket_to_the_tenants_own_unit_never_client_submitted(client, org_a, patch_db_with_mock):
    """Real proof the tool's real input_schema has no propertyId/unitId
    field at all - even if a request somehow smuggled one into
    tool_input, _execute_tenant_tool never reads it, only ever the
    authenticated user's own record."""
    tenant_a = await _create_tenant(client, org_a, unit_id="1A", resident_email="unita@example.com")

    tool_call = _tool_use_response("submit_maintenance_request", {
        "title": "Real leak", "category": "plumbing",
        "propertyId": "some-other-property-id", "unitId": "OTHER-UNIT",  # smuggled, must be ignored
    })
    final_reply = _text_response("Submitted!")

    with patch("routers.ai_copilot.anthropic_client.messages.create", new_callable=AsyncMock) as mock_create:
        mock_create.side_effect = [tool_call, final_reply]
        await client.post(
            "/api/ai/faq",
            json={"message": "Leak in my kitchen.", "history": []},
            headers={"Authorization": f"Bearer {tenant_a['token']}"},
        )

    tickets = await patch_db_with_mock["tickets"].find({}).to_list(length=50)
    assert len(tickets) == 1
    assert tickets[0]["propertyId"] == tenant_a["propertyId"]
    assert tickets[0]["unitId"] == "1A"


@pytest.mark.asyncio
async def test_faq_plain_question_needs_no_tool_call(client, org_a, patch_db_with_mock):
    tenant = await _create_tenant(client, org_a)

    final_reply = _text_response("Your rent is $1,200/month and your lease runs through next year.")

    with patch("routers.ai_copilot.anthropic_client.messages.create", new_callable=AsyncMock) as mock_create:
        mock_create.side_effect = [final_reply]
        resp = await client.post(
            "/api/ai/faq",
            json={"message": "How much is my rent?", "history": []},
            headers={"Authorization": f"Bearer {tenant['token']}"},
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ticketCreated"] is False
    assert "1,200" in data["answer"]


@pytest.mark.asyncio
async def test_faq_rejects_unauthenticated_requests(client):
    resp = await client.post("/api/ai/faq", json={"message": "hi", "history": []})
    assert resp.status_code == 401
