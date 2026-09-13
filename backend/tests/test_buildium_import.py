"""
Direct Buildium integration tests — real functional coverage against
MOCKED Buildium API responses (via respx), since testing against a
real, live customer Buildium account isn't possible here. The mocked
responses use field names and shapes matched directly against
Buildium's own published API documentation (developer.buildium.com).
If Buildium's actual live response differs in some field name this
pass couldn't fully verify, that's exactly what /preview's real-data
display exists to catch before /commit ever runs — see
routers/buildium_import.py's own module docstring.
"""
import respx
import httpx
import pytest

from tests.conftest import auth_headers

BUILDIUM_PROPERTY = {
    "Id": 501,
    "Name": "Maple Ridge Apartments",
    "Address": {"AddressLine1": "789 Maple Rd", "City": "Minneapolis", "State": "MN"},
}
BUILDIUM_UNIT = {"Id": 9001, "UnitNumber": "1A", "MarketRent": 1350, "Bedrooms": 2, "Bathrooms": 1, "UnitSize": 800}
BUILDIUM_LEASE = {
    "Id": 7001, "PropertyId": 501, "UnitId": 9001,
    "LeaseFromDate": "2026-01-01T00:00:00Z", "LeaseToDate": "2026-12-31T00:00:00Z",
    "Rent": 1350, "Tenants": [{"Id": 3001}],
}
BUILDIUM_TENANT = {
    "Id": 3001, "FirstName": "John", "LastName": "Smith",
    "Email": "john@example.com", "PhoneNumbers": [{"Number": "612-555-0199", "Type": "Mobile"}],
}


def _mock_buildium_api():
    """Registers all 4 real Buildium endpoints this integration calls,
    with realistic mocked responses. respx intercepts these at the
    httpx transport level, so the real request/response code in
    routers/buildium_import.py runs completely unmodified."""
    router = respx.mock(base_url="https://api.buildium.com/v1", assert_all_called=False)
    router.get("/rentals").mock(return_value=httpx.Response(200, json=[BUILDIUM_PROPERTY]))
    router.get("/rentals/501/units").mock(return_value=httpx.Response(200, json=[BUILDIUM_UNIT]))
    router.get("/leases").mock(return_value=httpx.Response(200, json=[BUILDIUM_LEASE]))
    router.get("/leases/tenants").mock(return_value=httpx.Response(200, json=[BUILDIUM_TENANT]))
    return router


@pytest.mark.asyncio
async def test_preview_returns_real_data_without_writing_to_db(client, org_a, patch_db_with_mock):
    with _mock_buildium_api():
        resp = await client.post(
            "/api/import/buildium/preview", headers=auth_headers(org_a),
            json={"clientId": "fake-id", "clientSecret": "fake-secret"},
        )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["propertyCount"] == 1
    assert data["unitCount"] == 1
    assert data["leaseCount"] == 1
    assert data["sampleProperties"][0]["name"] == "Maple Ridge Apartments"
    assert data["sampleLeases"][0]["residentName"] == "John Smith"

    # Real, critical assertion: preview must never write anything
    props = await patch_db_with_mock["properties"].find({"orgId": org_a["orgId"]}).to_list(length=10)
    assert props == []


@pytest.mark.asyncio
async def test_commit_creates_real_property_unit_and_lease(client, org_a, patch_db_with_mock):
    with _mock_buildium_api():
        resp = await client.post(
            "/api/import/buildium/commit", headers=auth_headers(org_a),
            json={"clientId": "fake-id", "clientSecret": "fake-secret"},
        )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["propertiesCreated"] == 1
    assert data["unitsAdded"] == 1
    assert data["leasesCreated"] == 1
    assert data["leaseErrors"] == []

    props = await patch_db_with_mock["properties"].find({"orgId": org_a["orgId"]}).to_list(length=10)
    assert len(props) == 1
    assert props[0]["name"] == "Maple Ridge Apartments"
    assert props[0]["units"][0]["unitId"] == "1A"
    assert props[0]["units"][0]["rent"] == 1350

    leases = await patch_db_with_mock["leases"].find({"orgId": org_a["orgId"]}).to_list(length=10)
    assert len(leases) == 1
    assert leases[0]["residentName"] == "John Smith"
    assert leases[0]["residentEmail"] == "john@example.com"
    assert leases[0]["inviteCode"]


@pytest.mark.asyncio
async def test_commit_is_idempotent_on_rerun(client, org_a, patch_db_with_mock):
    with _mock_buildium_api():
        await client.post(
            "/api/import/buildium/commit", headers=auth_headers(org_a),
            json={"clientId": "fake-id", "clientSecret": "fake-secret"},
        )
        resp2 = await client.post(
            "/api/import/buildium/commit", headers=auth_headers(org_a),
            json={"clientId": "fake-id", "clientSecret": "fake-secret"},
        )
    data2 = resp2.json()
    assert data2["propertiesCreated"] == 0
    assert data2["leasesCreated"] == 0

    props = await patch_db_with_mock["properties"].find({"orgId": org_a["orgId"]}).to_list(length=10)
    assert len(props) == 1
    assert len(props[0]["units"]) == 1
    leases = await patch_db_with_mock["leases"].find({"orgId": org_a["orgId"]}).to_list(length=10)
    assert len(leases) == 1


@pytest.mark.asyncio
async def test_bad_credentials_return_clean_error(client, org_a):
    router = respx.mock(base_url="https://api.buildium.com/v1", assert_all_called=False)
    router.get("/rentals").mock(return_value=httpx.Response(401, json={"UserMessage": "Unauthorized"}))
    with router:
        resp = await client.post(
            "/api/import/buildium/preview", headers=auth_headers(org_a),
            json={"clientId": "wrong-id", "clientSecret": "wrong-secret"},
        )
    assert resp.status_code == 400
    assert "credentials" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_buildium_import_never_crosses_organizations(client, org_a, org_b, patch_db_with_mock):
    with _mock_buildium_api():
        await client.post(
            "/api/import/buildium/commit", headers=auth_headers(org_a),
            json={"clientId": "fake-id", "clientSecret": "fake-secret"},
        )
    org_b_props = await patch_db_with_mock["properties"].find({"orgId": org_b["orgId"]}).to_list(length=10)
    assert org_b_props == []
