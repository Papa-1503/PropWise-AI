"""
Public vacancy feed + embeddable widget tests. Two real properties
verified: (1) the open CORS header is present on both the feed and
the widget script - required for the widget to actually work when
embedded on a customer's own external website; (2) multi-tenancy
isolation still holds even with CORS opened up - one org's vacancies
never leak into another org's feed.
"""
import pytest

from tests.conftest import auth_headers


@pytest.mark.asyncio
async def test_vacancies_feed_has_open_cors_header(client, org_a):
    resp = await client.get(f"/api/public/vacancies?orgId={org_a['orgId']}")
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == "*"


@pytest.mark.asyncio
async def test_vacancies_feed_requires_org_id(client):
    resp = await client.get("/api/public/vacancies")
    assert resp.status_code == 422  # missing required query param


@pytest.mark.asyncio
async def test_vacancies_feed_never_leaks_another_orgs_units(client, org_a, org_b, patch_db_with_mock):
    await patch_db_with_mock["properties"].insert_one({
        "name": "Org A Vacant Building", "orgId": org_a["orgId"],
        "units": [{"unitId": "1A", "status": "vacant", "rent": 1200, "bedrooms": 1, "bathrooms": 1}],
    })
    await patch_db_with_mock["properties"].insert_one({
        "name": "Org B Vacant Building", "orgId": org_b["orgId"],
        "units": [{"unitId": "2B", "status": "vacant", "rent": 1500, "bedrooms": 2, "bathrooms": 1}],
    })

    resp = await client.get(f"/api/public/vacancies?orgId={org_a['orgId']}")
    data = resp.json()
    property_names = [v["propertyName"] for v in data["vacancies"]]
    assert "Org A Vacant Building" in property_names
    assert "Org B Vacant Building" not in property_names


@pytest.mark.asyncio
async def test_vacancies_feed_excludes_occupied_units(client, org_a, patch_db_with_mock):
    await patch_db_with_mock["properties"].insert_one({
        "name": "Mixed Building", "orgId": org_a["orgId"],
        "units": [
            {"unitId": "1A", "status": "vacant", "rent": 1200, "bedrooms": 1, "bathrooms": 1},
            {"unitId": "1B", "status": "occupied", "rent": 1300, "bedrooms": 1, "bathrooms": 1},
        ],
    })
    resp = await client.get(f"/api/public/vacancies?orgId={org_a['orgId']}")
    data = resp.json()
    unit_ids = [v["unitId"] for v in data["vacancies"]]
    assert "1A" in unit_ids
    assert "1B" not in unit_ids


@pytest.mark.asyncio
async def test_widget_script_returns_javascript_with_open_cors(client):
    resp = await client.get("/api/public/vacancy-widget.js")
    assert resp.status_code == 200
    assert "javascript" in resp.headers["content-type"]
    assert resp.headers["access-control-allow-origin"] == "*"
    # Real, functional content checks - not just a content-type check
    assert "data-org-id" in resp.text
    assert "fetch(" in resp.text
    assert "/api/public/vacancies" in resp.text
