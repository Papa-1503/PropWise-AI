"""
Core auth tests — password verification, JWT requirement, and role
enforcement. Not exhaustive (auth.py has more surface than this file
covers, e.g. the HttpOnly cookie path, require_permission's custom-role
logic), but covers the fundamentals every other test in this suite
implicitly depends on already working correctly.
"""
import pytest

from conftest import auth_headers


@pytest.mark.asyncio
async def test_wrong_password_is_rejected(client, org_a):
    resp = await client.post("/api/auth/login", json={
        "email": org_a["email"], "password": "wrong-password",
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_correct_password_logs_in(client, org_a):
    resp = await client.post("/api/auth/login", json={
        "email": org_a["email"], "password": "testpass123",
    })
    assert resp.status_code == 200
    assert "accessToken" in resp.json()


@pytest.mark.asyncio
async def test_protected_endpoint_requires_a_token(client):
    resp = await client.get("/api/properties")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_garbage_token_is_rejected(client):
    resp = await client.get("/api/properties", headers={"Authorization": "Bearer not-a-real-jwt"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_tenant_cannot_reach_staff_only_endpoint(client, org_a):
    """A tenant account (role='tenant') must be rejected by
    require_staff-gated endpoints, not just role-gated in the
    frontend's UI. Creates a real tenant via the actual lease +
    register flow, matching how a real resident account comes into
    being."""
    from datetime import datetime, timedelta, timezone

    prop_resp = await client.post(
        "/api/properties",
        json={"name": "Auth Test Bldg", "address": "1 Auth St", "units": [
            {"unitId": "1", "status": "vacant", "rent": 1000},
        ]},
        headers=auth_headers(org_a),
    )
    property_id = prop_resp.json()["id"]

    now = datetime.now(timezone.utc)
    lease_resp = await client.post(
        "/api/leases",
        json={
            "propertyId": property_id, "unitId": "1", "residentName": "Auth Test Tenant",
            "residentEmail": "authtenant@example.com",
            "startDate": now.isoformat(), "endDate": (now + timedelta(days=365)).isoformat(),
            "rent": 1000,
        },
        headers=auth_headers(org_a),
    )
    invite_code = lease_resp.json()["inviteCode"]

    register_resp = await client.post("/api/auth/register", json={
        "inviteCode": invite_code, "name": "Auth Test Tenant",
        "email": "authtenant@example.com", "password": "tenantpass123",
    })
    tenant_token = register_resp.json()["accessToken"]

    # /api/staff is require_staff-gated - a tenant must never reach it
    resp = await client.get("/api/staff", headers={"Authorization": f"Bearer {tenant_token}"})
    assert resp.status_code == 403
