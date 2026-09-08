"""Minimal smoke tests validating the test infrastructure itself
(conftest.py's db patching + client/org fixtures) before anything else
in this suite depends on it."""
import pytest


@pytest.mark.asyncio
async def test_health_check(client):
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_org_a_and_org_b_are_genuinely_different_orgs(org_a, org_b):
    assert org_a["orgId"] != org_b["orgId"]
    assert org_a["userId"] != org_b["userId"]
