"""
Thermostat tests — confirms the real org-scoped device lookup, the
honest 501 when SEAM_API_KEY isn't configured (the real default in
this test environment, same as every other real integration in this
app), the real capability-flag check before setting an HVAC mode a
device can't perform, and real cross-org isolation.

seam_service's own network calls are mocked directly (patching the
async wrapper functions) - this app has never had live network access
to connect.getseam.com to test against for real, same honest caveat
already documented in seam_service.py's own module docstring for
smart locks.
"""
from unittest.mock import AsyncMock, patch

import pytest

from tests.conftest import auth_headers


async def _insert_property_with_unit(patch_db_with_mock, org_id, thermostat_device_id=None, unit_id="1A"):
    unit = {"unitId": unit_id, "status": "occupied", "rent": 1200}
    if thermostat_device_id:
        unit["seamThermostatDeviceId"] = thermostat_device_id
    result = await patch_db_with_mock["properties"].insert_one({
        "name": "Thermostat Test Bldg", "orgId": org_id, "units": [unit],
    })
    return str(result.inserted_id)


@pytest.mark.asyncio
async def test_list_devices_returns_501_when_seam_not_configured(client, org_a, patch_db_with_mock):
    """The real, honest default state in this environment - no
    SEAM_API_KEY is set, so this must fail loudly (501), never a
    silent empty list pretending to be a real answer."""
    resp = await client.get("/api/thermostats/devices", headers=auth_headers(org_a))
    assert resp.status_code == 501


@pytest.mark.asyncio
async def test_get_unit_thermostat_returns_400_when_no_device_linked(client, org_a, patch_db_with_mock):
    property_id = await _insert_property_with_unit(patch_db_with_mock, org_a["orgId"], thermostat_device_id=None)
    resp = await client.get(f"/api/thermostats/{property_id}/units/1A", headers=auth_headers(org_a))
    assert resp.status_code == 400
    assert "no thermostat linked" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_get_unit_thermostat_returns_real_device_state(client, org_a, patch_db_with_mock):
    property_id = await _insert_property_with_unit(patch_db_with_mock, org_a["orgId"], thermostat_device_id="dev-123")

    with patch("seam_service.get_thermostat_async", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {"device_id": "dev-123", "can_hvac_heat": True, "current_temperature_fahrenheit": 68}
        resp = await client.get(f"/api/thermostats/{property_id}/units/1A", headers=auth_headers(org_a))

    assert resp.status_code == 200, resp.text
    assert resp.json()["device"]["device_id"] == "dev-123"
    mock_get.assert_called_once_with("dev-123")


@pytest.mark.asyncio
async def test_set_mode_rejects_unsupported_capability(client, org_a, patch_db_with_mock):
    """A heat-only device must be rejected for "cool" - the real,
    honest capability check, not a blind forward to Seam."""
    property_id = await _insert_property_with_unit(patch_db_with_mock, org_a["orgId"], thermostat_device_id="dev-456")

    with patch("seam_service.get_thermostat_async", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {"device_id": "dev-456", "can_hvac_heat": True, "can_hvac_cool": False}
        resp = await client.post(
            f"/api/thermostats/{property_id}/units/1A/set-mode",
            json={"hvacMode": "cool", "coolingSetPointFahrenheit": 72},
            headers=auth_headers(org_a),
        )

    assert resp.status_code == 400
    assert "doesn't support cool mode" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_set_mode_succeeds_when_capability_present(client, org_a, patch_db_with_mock):
    property_id = await _insert_property_with_unit(patch_db_with_mock, org_a["orgId"], thermostat_device_id="dev-789")

    with patch("seam_service.get_thermostat_async", new_callable=AsyncMock) as mock_get, \
         patch("seam_service.set_hvac_mode_async", new_callable=AsyncMock) as mock_set:
        mock_get.return_value = {"device_id": "dev-789", "can_hvac_heat": True}
        mock_set.return_value = {"action_attempt": {"status": "success"}}
        resp = await client.post(
            f"/api/thermostats/{property_id}/units/1A/set-mode",
            json={"hvacMode": "heat", "heatingSetPointFahrenheit": 68},
            headers=auth_headers(org_a),
        )

    assert resp.status_code == 200, resp.text
    mock_set.assert_called_once_with("dev-789", "heat", 68, None)


@pytest.mark.asyncio
async def test_set_mode_off_never_requires_a_set_point(client, org_a, patch_db_with_mock):
    property_id = await _insert_property_with_unit(patch_db_with_mock, org_a["orgId"], thermostat_device_id="dev-off")

    with patch("seam_service.get_thermostat_async", new_callable=AsyncMock) as mock_get, \
         patch("seam_service.set_hvac_mode_async", new_callable=AsyncMock) as mock_set:
        mock_get.return_value = {"device_id": "dev-off", "can_turn_off_hvac": True}
        mock_set.return_value = {"action_attempt": {"status": "success"}}
        resp = await client.post(
            f"/api/thermostats/{property_id}/units/1A/set-mode",
            json={"hvacMode": "off"},
            headers=auth_headers(org_a),
        )

    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_cannot_access_a_different_orgs_unit_thermostat(client, org_a, org_b, patch_db_with_mock):
    property_id = await _insert_property_with_unit(patch_db_with_mock, org_b["orgId"], thermostat_device_id="dev-orgb")
    resp = await client.get(f"/api/thermostats/{property_id}/units/1A", headers=auth_headers(org_a))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_rejects_unauthenticated_requests(client):
    resp = await client.get("/api/thermostats/devices")
    assert resp.status_code == 401
