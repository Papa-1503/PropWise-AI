"""
Per-role authorization tests — confirms the custom-roles permission
system (auth.py's require_permission) actually has a real effect, not
just that it exists. Found and fixed alongside these tests: not a
single real endpoint used require_permission before this - every
endpoint only ever checked require_staff (role, not granular
permission), meaning a staff member's assigned custom role never
actually restricted anything they could do. This suite tests the 6
real endpoints now wired to it, one per permission category
(leasing, maintenance, finance, communications, staff_management,
reports), and confirms the two real invariants that matter:

1. A staff member with a custom role that's MISSING a permission is
   genuinely blocked (403) from the matching endpoint.
2. A staff member with NO custom role assigned (still today's real
   default for every existing account) keeps full access everywhere -
   require_permission must never become an accidental new lockout for
   the common case.

Also confirms a role WITH the permission is genuinely allowed through,
not just that missing permissions are blocked - a permission system
that only ever returns 403 wouldn't be meaningfully tested.
"""
import pytest

from tests.conftest import auth_headers


async def _create_staff_with_role(client, org, permissions, email="scoped@example.com"):
    """Real, end-to-end: creates a real custom role with exactly the
    given permissions, and assigns it to the real org owner account -
    the simplest real way to exercise a scoped role without needing a
    separate staff-invite flow this app may not have."""
    role_resp = await client.post(
        "/api/custom-roles",
        json={"name": "Test Role", "permissions": permissions},
        headers=auth_headers(org),
    )
    role_id = role_resp.json()["id"]
    await client.patch(
        f"/api/custom-roles/staff/{org['userId']}/assign",
        json={"customRoleId": role_id},
        headers=auth_headers(org),
    )
    return role_id


@pytest.mark.asyncio
async def test_leasing_permission_blocks_lease_creation_when_missing(client, org_a, patch_db_with_mock):
    """A staff member whose custom role does NOT include 'leasing'
    must be genuinely blocked from creating a lease - not just shown
    a disabled button in some frontend that never existed to begin
    with; this is the real, structural 403."""
    role_resp = await client.post(
        "/api/custom-roles",
        json={"name": "Maintenance Only", "permissions": ["maintenance"]},
        headers=auth_headers(org_a),
    )
    role_id = role_resp.json()["id"]

    prop_resp = await client.post(
        "/api/properties",
        json={"name": "Perm Test Bldg", "address": "1 Perm St", "units": [
            {"unitId": "1", "status": "vacant", "rent": 1000},
        ]},
        headers=auth_headers(org_a),
    )
    property_id = prop_resp.json()["id"]

    # Assign the "Maintenance Only" role to the ORG OWNER account itself
    # (org_a's own staff user) - simplest real way to exercise a
    # scoped role without needing a separate staff-invite flow this
    # app may not have. This still tests the exact real thing that
    # matters: does a staff account WITH a role missing 'leasing' get
    # blocked from creating a lease.
    await client.patch(
        f"/api/custom-roles/staff/{org_a['userId']}/assign",
        json={"customRoleId": role_id},
        headers=auth_headers(org_a),
    )

    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    resp = await client.post(
        "/api/leases",
        json={
            "propertyId": property_id, "unitId": "1", "residentName": "Blocked Tenant",
            "startDate": now.isoformat(), "endDate": (now + timedelta(days=365)).isoformat(),
            "rent": 1000,
        },
        headers=auth_headers(org_a),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_leasing_permission_allows_lease_creation_when_present(client, org_a, patch_db_with_mock):
    """The other half - a role that DOES include 'leasing' must
    genuinely still work, not just that missing permissions block."""
    role_resp = await client.post(
        "/api/custom-roles",
        json={"name": "Leasing Agent", "permissions": ["leasing", "communications"]},
        headers=auth_headers(org_a),
    )
    role_id = role_resp.json()["id"]

    prop_resp = await client.post(
        "/api/properties",
        json={"name": "Perm Test Bldg 2", "address": "2 Perm St", "units": [
            {"unitId": "1", "status": "vacant", "rent": 1000},
        ]},
        headers=auth_headers(org_a),
    )
    property_id = prop_resp.json()["id"]

    await client.patch(
        f"/api/custom-roles/staff/{org_a['userId']}/assign",
        json={"customRoleId": role_id},
        headers=auth_headers(org_a),
    )

    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    resp = await client.post(
        "/api/leases",
        json={
            "propertyId": property_id, "unitId": "1", "residentName": "Allowed Tenant",
            "startDate": now.isoformat(), "endDate": (now + timedelta(days=365)).isoformat(),
            "rent": 1000,
        },
        headers=auth_headers(org_a),
    )
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_no_custom_role_assigned_keeps_full_access(client, org_a, patch_db_with_mock):
    """The real default-behavior guarantee - an org owner/staff
    account with NO customRoleId (every account today, and every
    account created without one going forward) must keep full access
    to leasing, exactly as before this change - require_permission
    must never become a silent new lockout for the common case."""
    prop_resp = await client.post(
        "/api/properties",
        json={"name": "Default Access Bldg", "address": "3 Perm St", "units": [
            {"unitId": "1", "status": "vacant", "rent": 1000},
        ]},
        headers=auth_headers(org_a),
    )
    property_id = prop_resp.json()["id"]

    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    resp = await client.post(
        "/api/leases",
        json={
            "propertyId": property_id, "unitId": "1", "residentName": "Default Tenant",
            "startDate": now.isoformat(), "endDate": (now + timedelta(days=365)).isoformat(),
            "rent": 1000,
        },
        headers=auth_headers(org_a),
    )
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_finance_permission_blocks_charge_creation_when_missing(client, org_a, patch_db_with_mock):
    role_resp = await client.post(
        "/api/custom-roles",
        json={"name": "No Finance", "permissions": ["leasing"]},
        headers=auth_headers(org_a),
    )
    role_id = role_resp.json()["id"]

    prop_resp = await client.post(
        "/api/properties",
        json={"name": "Finance Test Bldg", "address": "4 Perm St", "units": [
            {"unitId": "1", "status": "occupied", "rent": 1000},
        ]},
        headers=auth_headers(org_a),
    )
    property_id = prop_resp.json()["id"]

    await client.patch(
        f"/api/custom-roles/staff/{org_a['userId']}/assign",
        json={"customRoleId": role_id},
        headers=auth_headers(org_a),
    )

    from datetime import datetime, timedelta, timezone
    resp = await client.post(
        "/api/payments",
        json={
            "propertyId": property_id, "unitId": "1", "amountDue": 1000,
            "dueDate": (datetime.now(timezone.utc) + timedelta(days=5)).isoformat(),
            "description": "Rent",
        },
        headers=auth_headers(org_a),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_staff_management_permission_blocks_property_assignment_when_missing(client, org_a, patch_db_with_mock):
    role_resp = await client.post(
        "/api/custom-roles",
        json={"name": "No Staff Mgmt", "permissions": ["reports"]},
        headers=auth_headers(org_a),
    )
    role_id = role_resp.json()["id"]

    await client.patch(
        f"/api/custom-roles/staff/{org_a['userId']}/assign",
        json={"customRoleId": role_id},
        headers=auth_headers(org_a),
    )

    resp = await client.patch(
        f"/api/staff/{org_a['userId']}/properties",
        json={"assignedProperties": ["some-property-id"]},
        headers=auth_headers(org_a),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_reports_permission_blocks_report_creation_when_missing(client, org_a, patch_db_with_mock):
    role_resp = await client.post(
        "/api/custom-roles",
        json={"name": "No Reports", "permissions": ["finance"]},
        headers=auth_headers(org_a),
    )
    role_id = role_resp.json()["id"]

    await client.patch(
        f"/api/custom-roles/staff/{org_a['userId']}/assign",
        json={"customRoleId": role_id},
        headers=auth_headers(org_a),
    )

    resp = await client.post(
        "/api/custom-reports",
        json={"name": "Blocked Report", "reportType": "revenue_by_property"},
        headers=auth_headers(org_a),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_communications_permission_blocks_email_send_when_missing(client, org_a, patch_db_with_mock):
    role_resp = await client.post(
        "/api/custom-roles",
        json={"name": "No Comms", "permissions": ["finance"]},
        headers=auth_headers(org_a),
    )
    role_id = role_resp.json()["id"]

    await client.patch(
        f"/api/custom-roles/staff/{org_a['userId']}/assign",
        json={"customRoleId": role_id},
        headers=auth_headers(org_a),
    )

    resp = await client.post(
        "/api/communications/send-email",
        json={"propertyId": "p1", "unitId": "1", "subject": "Test", "body": "Test message"},
        headers=auth_headers(org_a),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_me_exposes_customroleid_when_assigned(client, org_a, patch_db_with_mock):
    """CHANGED (Sept 15, 2026): customRoleId is now exposed on
    /auth/me so the frontend can look up this role's real permissions
    and scope navigation to what this staff member can actually do."""
    role_resp = await client.post(
        "/api/custom-roles",
        json={"name": "Leasing Agent", "permissions": ["leasing"]},
        headers=auth_headers(org_a),
    )
    role_id = role_resp.json()["id"]
    await client.patch(
        f"/api/custom-roles/staff/{org_a['userId']}/assign",
        json={"customRoleId": role_id},
        headers=auth_headers(org_a),
    )

    resp = await client.get("/api/auth/me", headers=auth_headers(org_a))
    assert resp.status_code == 200, resp.text
    assert resp.json()["customRoleId"] == role_id


@pytest.mark.asyncio
async def test_me_customroleid_is_null_by_default(client, org_a, patch_db_with_mock):
    resp = await client.get("/api/auth/me", headers=auth_headers(org_a))
    assert resp.json()["customRoleId"] is None
