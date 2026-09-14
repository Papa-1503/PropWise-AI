"""
Onboarding assistant tests — Claude's own API calls are mocked (no
real API cost per test run, and fully deterministic), using REAL
anthropic SDK block types (TextBlock, ToolUseBlock) so the mocked
responses have the exact same shape the real API returns, including
model_dump() support, which the router's own tool-use loop relies on.
What's under real test here is this app's own logic: does a tool call
Claude requests actually result in a real, correctly-scoped database
write; is org isolation preserved; does the loop terminate correctly
on a text-only response.
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
async def test_status_reflects_real_counts(client, org_a, patch_db_with_mock):
    resp = await client.get("/api/onboarding/status", headers=auth_headers(org_a))
    assert resp.status_code == 200
    data = resp.json()
    assert data["propertyCount"] == 0
    assert data["leaseCount"] == 0
    assert data["setupComplete"] is False

    await patch_db_with_mock["properties"].insert_one({"name": "Test", "orgId": org_a["orgId"], "units": []})
    resp2 = await client.get("/api/onboarding/status", headers=auth_headers(org_a))
    assert resp2.json()["propertyCount"] == 1


@pytest.mark.asyncio
async def test_chat_creates_property_via_real_tool_call(client, org_a, patch_db_with_mock):
    tool_call = _tool_use_response("create_property", {
        "name": "Maple Ridge", "address": "789 Maple Rd",
        "units": [{"unitId": "1A", "rent": 1200, "bedrooms": 1, "bathrooms": 1}],
    })
    final_reply = _text_response("Great, I've added Maple Ridge with unit 1A!")

    with patch("routers.onboarding_assistant.anthropic_client.messages.create", new_callable=AsyncMock) as mock_create:
        mock_create.side_effect = [tool_call, final_reply]
        resp = await client.post(
            "/api/onboarding/chat",
            json={"message": "I have a property called Maple Ridge at 789 Maple Rd with one unit, 1A, $1200/mo, 1 bed 1 bath.", "history": []},
            headers=auth_headers(org_a),
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "Maple Ridge" in data["reply"]
    assert data["status"]["propertyCount"] == 1

    props = await patch_db_with_mock["properties"].find({"orgId": org_a["orgId"]}).to_list(length=10)
    assert len(props) == 1
    assert props[0]["name"] == "Maple Ridge"
    assert props[0]["units"][0]["unitId"] == "1A"


@pytest.mark.asyncio
async def test_chat_creates_lease_via_real_tool_call(client, org_a, patch_db_with_mock):
    await patch_db_with_mock["properties"].insert_one({
        "name": "Maple Ridge", "orgId": org_a["orgId"],
        "units": [{"unitId": "1A", "rent": 1200, "bedrooms": 1, "bathrooms": 1}],
    })

    tool_call = _tool_use_response("create_lease", {
        "propertyName": "Maple Ridge", "unitId": "1A", "residentName": "Jane Doe",
        "startDate": "2026-10-01", "endDate": "2027-09-30", "rent": 1200,
    })
    final_reply = _text_response("Done — Jane Doe's lease is set up. Next, let's get you subscribed under Settings > Billing.")

    with patch("routers.onboarding_assistant.anthropic_client.messages.create", new_callable=AsyncMock) as mock_create:
        mock_create.side_effect = [tool_call, final_reply]
        resp = await client.post(
            "/api/onboarding/chat",
            json={"message": "Add a lease for Jane Doe in unit 1A, starting Oct 1 2026 for a year at $1200/mo.", "history": []},
            headers=auth_headers(org_a),
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"]["leaseCount"] == 1
    assert data["status"]["setupComplete"] is True

    leases = await patch_db_with_mock["leases"].find({"orgId": org_a["orgId"]}).to_list(length=10)
    assert len(leases) == 1
    assert leases[0]["residentName"] == "Jane Doe"
    assert leases[0]["inviteCode"]


@pytest.mark.asyncio
async def test_chat_lease_for_nonexistent_property_gives_honest_error_not_a_crash(client, org_a, patch_db_with_mock):
    tool_call = _tool_use_response("create_lease", {
        "propertyName": "Nonexistent Place", "unitId": "1A", "residentName": "John",
        "startDate": "2026-10-01", "endDate": "2027-09-30", "rent": 1000,
    })
    final_reply = _text_response("I couldn't find a property by that name yet — let's add the property first.")

    with patch("routers.onboarding_assistant.anthropic_client.messages.create", new_callable=AsyncMock) as mock_create:
        mock_create.side_effect = [tool_call, final_reply]
        resp = await client.post(
            "/api/onboarding/chat",
            json={"message": "Add a lease for John in Nonexistent Place.", "history": []},
            headers=auth_headers(org_a),
        )

    assert resp.status_code == 200, resp.text
    leases = await patch_db_with_mock["leases"].find({"orgId": org_a["orgId"]}).to_list(length=10)
    assert leases == []


@pytest.mark.asyncio
async def test_chat_with_no_tool_call_just_returns_text(client, org_a):
    final_reply = _text_response("Sure! What's the name of your first property?")
    with patch("routers.onboarding_assistant.anthropic_client.messages.create", new_callable=AsyncMock) as mock_create:
        mock_create.side_effect = [final_reply]
        resp = await client.post(
            "/api/onboarding/chat",
            json={"message": "Hi, I'd like help setting up.", "history": []},
            headers=auth_headers(org_a),
        )
    assert resp.status_code == 200
    assert "property" in resp.json()["reply"].lower()


@pytest.mark.asyncio
async def test_chat_tool_creation_is_scoped_to_callers_own_org(client, org_a, org_b, patch_db_with_mock):
    tool_call = _tool_use_response("create_property", {
        "name": "Org A Only Property", "address": "1 Test St",
        "units": [{"unitId": "1", "rent": 1000, "bedrooms": 1, "bathrooms": 1}],
    })
    final_reply = _text_response("Added!")

    with patch("routers.onboarding_assistant.anthropic_client.messages.create", new_callable=AsyncMock) as mock_create:
        mock_create.side_effect = [tool_call, final_reply]
        await client.post(
            "/api/onboarding/chat",
            json={"message": "Add a property.", "history": []},
            headers=auth_headers(org_a),
        )

    org_b_props = await patch_db_with_mock["properties"].find({"orgId": org_b["orgId"]}).to_list(length=10)
    assert org_b_props == []
    org_a_props = await patch_db_with_mock["properties"].find({"orgId": org_a["orgId"]}).to_list(length=10)
    assert len(org_a_props) == 1


@pytest.mark.asyncio
async def test_chat_rejects_unauthenticated_requests(client, org_a):
    """require_staff (Depends(get_current_user) underneath) rejects a
    request with no real session at all - the simplest, most direct
    proof the dependency is genuinely applied to this router."""
    resp = await client.post("/api/onboarding/chat", json={"message": "hi", "history": []})
    assert resp.status_code == 401
