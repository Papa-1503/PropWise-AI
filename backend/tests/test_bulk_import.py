"""
Bulk CSV import tests — real functional coverage for
routers/bulk_import.py, including the specific claims made in its own
docstrings: idempotent re-runs never create duplicates, a bad row
never aborts the whole import, and one organization's import can
never affect another's data.
"""
import pytest

from tests.conftest import auth_headers


PROPERTIES_CSV = (
    "property_name,address,unit_id,bedrooms,bathrooms,rent,square_footage,status\n"
    "Sunset Apartments,123 Main St,101,2,1,1450,850,occupied\n"
    "Sunset Apartments,123 Main St,102,1,1,1100,600,vacant\n"
    "Maple Grove,456 Oak Ave,201,3,2,1800,1100,vacant\n"
)

LEASES_CSV = (
    "property_name,unit_id,resident_name,resident_email,resident_phone,start_date,end_date,rent,deposit_amount\n"
    "Sunset Apartments,101,Jane Doe,jane@example.com,612-555-0100,2026-01-01,2026-12-31,1450,1450\n"
)


def _csv_file(content: str, filename: str = "data.csv"):
    return {"file": (filename, content, "text/csv")}


@pytest.mark.asyncio
async def test_import_properties_creates_grouped_properties_and_units(client, org_a, patch_db_with_mock):
    resp = await client.post("/api/import/properties", headers=auth_headers(org_a), files=_csv_file(PROPERTIES_CSV))
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["propertiesCreated"] == 2  # Sunset Apartments + Maple Grove
    assert data["unitsAdded"] == 3
    assert data["errors"] == []

    props = await patch_db_with_mock["properties"].find({"orgId": org_a["orgId"]}).to_list(length=10)
    sunset = next(p for p in props if p["name"] == "Sunset Apartments")
    assert len(sunset["units"]) == 2
    assert {u["unitId"] for u in sunset["units"]} == {"101", "102"}


@pytest.mark.asyncio
async def test_import_properties_is_idempotent_on_rerun(client, org_a, patch_db_with_mock):
    """The exact claim in the module docstring: re-running the same
    file must never create duplicate properties or duplicate units."""
    resp1 = await client.post("/api/import/properties", headers=auth_headers(org_a), files=_csv_file(PROPERTIES_CSV))
    assert resp1.status_code == 200

    resp2 = await client.post("/api/import/properties", headers=auth_headers(org_a), files=_csv_file(PROPERTIES_CSV))
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["propertiesCreated"] == 0
    assert data2["unitsAdded"] == 0
    assert any("already existed" in e for e in data2["errors"])

    props = await patch_db_with_mock["properties"].find({"orgId": org_a["orgId"]}).to_list(length=10)
    assert len(props) == 2  # still exactly 2 properties, not 4
    sunset = next(p for p in props if p["name"] == "Sunset Apartments")
    assert len(sunset["units"]) == 2  # still exactly 2 units, not 4


@pytest.mark.asyncio
async def test_import_properties_bad_row_does_not_abort_whole_import(client, org_a, patch_db_with_mock):
    """One malformed row must fail on its own, with a clear reason -
    every other valid row in the same file must still succeed."""
    csv_with_bad_row = (
        "property_name,address,unit_id,bedrooms,bathrooms,rent,square_footage,status\n"
        "Good Property,1 Elm St,101,2,1,1450,850,occupied\n"
        "Bad Property,2 Elm St,201,not-a-number,1,1200,700,vacant\n"
    )
    resp = await client.post("/api/import/properties", headers=auth_headers(org_a), files=_csv_file(csv_with_bad_row))
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["propertiesCreated"] == 1  # only "Good Property" - "Bad Property" had zero valid units
    assert len(data["errors"]) == 1
    assert "bedrooms" in data["errors"][0]

    props = await patch_db_with_mock["properties"].find({"orgId": org_a["orgId"]}).to_list(length=10)
    assert len(props) == 1
    assert props[0]["name"] == "Good Property"


@pytest.mark.asyncio
async def test_import_leases_against_existing_property(client, org_a, patch_db_with_mock):
    await client.post("/api/import/properties", headers=auth_headers(org_a), files=_csv_file(PROPERTIES_CSV))

    resp = await client.post("/api/import/leases", headers=auth_headers(org_a), files=_csv_file(LEASES_CSV))
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["leasesCreated"] == 1
    assert data["errors"] == []

    leases = await patch_db_with_mock["leases"].find({"orgId": org_a["orgId"]}).to_list(length=10)
    assert len(leases) == 1
    assert leases[0]["residentName"] == "Jane Doe"
    assert leases[0]["inviteCode"]  # a real invite code was generated, same as manual lease creation


@pytest.mark.asyncio
async def test_import_leases_fails_cleanly_for_unknown_property(client, org_a, patch_db_with_mock):
    resp = await client.post("/api/import/leases", headers=auth_headers(org_a), files=_csv_file(LEASES_CSV))
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["leasesCreated"] == 0
    assert len(data["errors"]) == 1
    assert "no property named" in data["errors"][0]


@pytest.mark.asyncio
async def test_import_leases_is_idempotent_on_rerun(client, org_a, patch_db_with_mock):
    await client.post("/api/import/properties", headers=auth_headers(org_a), files=_csv_file(PROPERTIES_CSV))
    resp1 = await client.post("/api/import/leases", headers=auth_headers(org_a), files=_csv_file(LEASES_CSV))
    assert resp1.json()["leasesCreated"] == 1

    resp2 = await client.post("/api/import/leases", headers=auth_headers(org_a), files=_csv_file(LEASES_CSV))
    data2 = resp2.json()
    assert data2["leasesCreated"] == 0
    assert any("already exists" in e for e in data2["errors"])

    leases = await patch_db_with_mock["leases"].find({"orgId": org_a["orgId"]}).to_list(length=10)
    assert len(leases) == 1  # still exactly 1, not 2


@pytest.mark.asyncio
async def test_import_never_crosses_organizations(client, org_a, org_b, patch_db_with_mock):
    """The real multi-tenancy claim: Org A's import must be completely
    invisible to Org B, and Org B must not be able to import leases
    against Org A's properties even by naming them exactly."""
    await client.post("/api/import/properties", headers=auth_headers(org_a), files=_csv_file(PROPERTIES_CSV))

    # Org B has never imported anything - its own properties list must be empty
    org_b_props = await patch_db_with_mock["properties"].find({"orgId": org_b["orgId"]}).to_list(length=10)
    assert org_b_props == []

    # Org B trying to import a lease against Org A's real property name must fail cleanly
    resp = await client.post("/api/import/leases", headers=auth_headers(org_b), files=_csv_file(LEASES_CSV))
    data = resp.json()
    assert data["leasesCreated"] == 0
    assert "no property named" in data["errors"][0]


@pytest.mark.asyncio
async def test_import_rejects_non_csv_file(client, org_a):
    resp = await client.post(
        "/api/import/properties", headers=auth_headers(org_a),
        files={"file": ("data.txt", "not a real csv", "text/plain")},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_import_rejects_missing_required_columns(client, org_a):
    bad_csv = "some_column,other_column\nvalue1,value2\n"
    resp = await client.post("/api/import/properties", headers=auth_headers(org_a), files=_csv_file(bad_csv))
    assert resp.status_code == 400
    assert "Missing required column" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_download_templates_return_valid_csv(client, org_a):
    resp = await client.get("/api/import/properties/template", headers=auth_headers(org_a))
    assert resp.status_code == 200
    assert "property_name" in resp.text
    assert "Sunset Apartments" in resp.text

    resp2 = await client.get("/api/import/leases/template", headers=auth_headers(org_a))
    assert resp2.status_code == 200
    assert "resident_name" in resp2.text
