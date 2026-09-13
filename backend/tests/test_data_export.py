"""
Customer data export tests — verifies the real, important properties:
an org's own data is actually included, another org's data is never
leaked into the export, non-owner staff can't reach it, and the
response is real, valid, re-parseable JSON with correct BSON types.
"""
import pytest
from bson import json_util

from tests.conftest import auth_headers


@pytest.mark.asyncio
async def test_export_includes_the_orgs_own_real_data(client, org_a, patch_db_with_mock):
    await patch_db_with_mock["properties"].insert_one({
        "name": "Sunset Apartments", "orgId": org_a["orgId"], "units": [{"unitId": "101"}],
    })
    await patch_db_with_mock["leases"].insert_one({
        "propertyId": "p1", "unitId": "101", "residentName": "Jane Doe", "orgId": org_a["orgId"],
    })

    resp = await client.get("/api/organizations/me/export", headers=auth_headers(org_a))
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/json"
    assert "attachment" in resp.headers["content-disposition"]

    data = json_util.loads(resp.text)
    assert data["organization"]["name"] == "Org A"
    assert len(data["properties"]) == 1
    assert data["properties"][0]["name"] == "Sunset Apartments"
    assert len(data["leases"]) == 1
    assert data["leases"][0]["residentName"] == "Jane Doe"
    assert len(data["users"]) >= 1


@pytest.mark.asyncio
async def test_export_never_leaks_another_orgs_data(client, org_a, org_b, patch_db_with_mock):
    await patch_db_with_mock["properties"].insert_one({
        "name": "Org A Building", "orgId": org_a["orgId"], "units": [],
    })
    await patch_db_with_mock["properties"].insert_one({
        "name": "Org B Building", "orgId": org_b["orgId"], "units": [],
    })

    resp = await client.get("/api/organizations/me/export", headers=auth_headers(org_a))
    data = json_util.loads(resp.text)

    property_names = [p["name"] for p in data["properties"]]
    assert "Org A Building" in property_names
    assert "Org B Building" not in property_names
    assert data["organization"]["name"] == "Org A"


@pytest.mark.asyncio
async def test_export_rejects_non_owner_staff(client, org_a):
    register_resp = await client.post(
        "/api/auth/register-staff",
        json={"name": "Team Mate", "email": "exportteammate@example.com", "password": "teammatepass123"},
        headers=auth_headers(org_a),
    )
    assert register_resp.status_code == 200, register_resp.text
    teammate_token = register_resp.json()["accessToken"]

    resp = await client.get("/api/organizations/me/export", headers={"Authorization": f"Bearer {teammate_token}"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_export_response_is_real_valid_json_with_correct_bson_types(client, org_a, patch_db_with_mock):
    """A real, re-parseable file - datetimes and ObjectIds must
    round-trip correctly via bson.json_util, not become opaque
    strings or crash plain json.loads."""
    resp = await client.get("/api/organizations/me/export", headers=auth_headers(org_a))
    data = json_util.loads(resp.text)

    from datetime import datetime
    from bson import ObjectId
    assert isinstance(data["organization"]["_id"], ObjectId)
    assert isinstance(data["organization"]["createdAt"], datetime)
    assert "exportedAt" in data


@pytest.mark.asyncio
async def test_export_excludes_sensitive_transient_collections(client, org_a):
    """password_reset_tokens and photo_upload_tokens are deliberately
    never included - see the router's own module docstring for why."""
    resp = await client.get("/api/organizations/me/export", headers=auth_headers(org_a))
    data = json_util.loads(resp.text)

    assert "passwordResetTokens" not in data
    assert "photoUploadTokens" not in data
    assert "schedulerHealth" not in data
