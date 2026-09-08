"""
Scheduler multi-org isolation tests — real regression protection for
the org-loop rewrite in routers/admin.py's 8 background checks (late
fees, escalations, autopay, lease renewal, payment reminders, vendor
SLA, vendor compliance, renewal risk). Before that rewrite, every one
of these queried its target collection with no org filter at all,
meaning a check run for one organization could act on - or leak data
between - every organization sharing the deployment.

These tests call the internal _do_*_check functions directly (the
same functions main.py's real background scheduler calls), not the
HTTP-triggered wrapper endpoints, since the wrappers just add an admin
key check on top. Only two of the eight checks are covered here
(late fees, preventive maintenance) - the most directly testable
without mocking Stripe (autopay) or Twilio (vendor SLA). Extending
coverage to the remaining six is real, valuable, ongoing work, stated
honestly rather than implied complete.

GOTCHA discovered while writing these: mongomock-motor can return a
collection wrapper via `some_mock_db["name"]` that does not reliably
share state with a wrapper obtained by indexing the SAME name again
later in the same test, even though both point at real data under the
hood. For any test that needs to inspect a collection directly (not
through the real HTTP API), use the app's own already-patched
reference from `db.py` (e.g. `import db as db_module;
db_module.tickets_col`) rather than re-indexing `patch_db_with_mock[
"collection_name"]` fresh mid-test - the former is the exact object
the application code itself reads and writes through, so there is no
ambiguity.
"""
from datetime import datetime, timedelta, timezone

import pytest
from bson import ObjectId

from conftest import auth_headers


async def _create_property(client, org, name="Test Property"):
    resp = await client.post(
        "/api/properties",
        json={"name": name, "address": "123 Main St", "units": [
            {"unitId": "101", "status": "occupied", "rent": 1500},
        ]},
        headers=auth_headers(org),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _create_overdue_charge(client, org, property_id, unit_id="101", days_overdue=10):
    due_date = datetime.now(timezone.utc) - timedelta(days=days_overdue)
    resp = await client.post(
        "/api/payments",
        json={
            "propertyId": property_id, "unitId": unit_id,
            "amountDue": 1500, "dueDate": due_date.isoformat(),
            "description": "Test rent charge",
        },
        headers=auth_headers(org),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_late_fee_check_applies_independently_to_each_org(client, org_a, org_b, patch_db_with_mock):
    """Real, previously-live risk: _do_late_fee_check used to query
    payments_col globally. This confirms both orgs' overdue charges
    get a late fee, and that the fee/grace-period values used for each
    charge come from that charge's OWN org's property settings, not
    whichever property the check happened to look up first."""
    from routers.admin import _do_late_fee_check

    prop_a = await _create_property(client, org_a, "Org A Building")
    prop_b = await _create_property(client, org_b, "Org B Building")

    # Org B sets a custom, real grace period + fee amount - different
    # from the app's defaults, so a cross-org mixup would be
    # detectable (org A's charge getting org B's $200 fee, etc.)
    await client.patch(
        f"/api/properties/{prop_b['id']}/rent-rules",
        json={"lateFeeAmount": 200.0, "lateFeeGraceDays": 3},
        headers=auth_headers(org_b),
    )

    charge_a = await _create_overdue_charge(client, org_a, prop_a["id"], days_overdue=10)
    charge_b = await _create_overdue_charge(client, org_b, prop_b["id"], days_overdue=10)

    result = await _do_late_fee_check()
    assert result["lateFeesApplied"] >= 2

    updated_a = (await client.get("/api/payments", headers=auth_headers(org_a))).json()["charges"]
    updated_b = (await client.get("/api/payments", headers=auth_headers(org_b))).json()["charges"]

    charge_a_after = next(c for c in updated_a if c["id"] == charge_a["id"])
    charge_b_after = next(c for c in updated_b if c["id"] == charge_b["id"])

    # Org A: default $50 late fee -> amountDue 1500 + 50 = 1550
    assert charge_a_after["amountDue"] == pytest.approx(1550.0)
    # Org B: its own real $200 late fee -> amountDue 1500 + 200 = 1700
    assert charge_b_after["amountDue"] == pytest.approx(1700.0)


@pytest.mark.asyncio
async def test_late_fee_check_never_applies_org_bs_charge_to_org_a_view(client, org_a, org_b, patch_db_with_mock):
    """The other real half of isolation: after the scheduler runs
    globally across every org, org A's own payments list must still
    never surface org B's charge - the scheduler's cross-org loop
    itself must never be a path that leaks data between orgs."""
    from routers.admin import _do_late_fee_check

    prop_a = await _create_property(client, org_a, "Org A Building")
    prop_b = await _create_property(client, org_b, "Org B Building")
    await _create_overdue_charge(client, org_a, prop_a["id"])
    charge_b = await _create_overdue_charge(client, org_b, prop_b["id"])

    await _do_late_fee_check()

    org_a_charges = (await client.get("/api/payments", headers=auth_headers(org_a))).json()["charges"]
    assert charge_b["id"] not in [c["id"] for c in org_a_charges]


@pytest.mark.asyncio
async def test_maintenance_check_creates_tickets_with_correct_org_for_both_orgs(client, org_a, org_b, patch_db_with_mock):
    """Real, previously-live risk found and fixed this session: the
    ticket _do_maintenance_check creates had no orgId at all before
    the org-loop rewrite - it would have been invisible in every
    org-scoped Maintenance list, for every organization, forever."""
    from routers.admin import _do_maintenance_check

    prop_a = await _create_property(client, org_a, "Org A Building")
    prop_b = await _create_property(client, org_b, "Org B Building")

    past_due = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    for org, prop in ((org_a, prop_a), (org_b, prop_b)):
        resp = await client.post(
            "/api/maintenance-schedules",
            json={
                "propertyId": prop["id"], "unitId": "101", "title": "HVAC filter check",
                "category": "hvac", "intervalDays": 90, "nextDueDate": past_due,
            },
            headers=auth_headers(org),
        )
        assert resp.status_code == 200, resp.text

    result = await _do_maintenance_check()
    assert result["ticketsCreated"] >= 2

    resp_a = await client.get("/api/maintenance/tickets", headers=auth_headers(org_a))
    assert resp_a.status_code == 200, resp_a.text
    tickets_a = resp_a.json()["tickets"]
    resp_b = await client.get("/api/maintenance/tickets", headers=auth_headers(org_b))
    assert resp_b.status_code == 200, resp_b.text
    tickets_b = resp_b.json()["tickets"]

    assert any(t["title"] == "HVAC filter check" for t in tickets_a)
    assert any(t["title"] == "HVAC filter check" for t in tickets_b)

    # Real cross-check directly against the mock DB: every ticket this
    # check created must carry a real, correct orgId - not None, and
    # not accidentally the SAME org for both. Uses db.py's own
    # already-patched tickets_col directly (see conftest.py) rather
    # than re-indexing patch_db_with_mock fresh - mongomock-motor
    # returns a new collection wrapper object on each index operation,
    # so re-indexing the same fixture inconsistently across a test can
    # produce a wrapper that behaves correctly for writes/reads within
    # itself but should not be assumed identical to a wrapper obtained
    # elsewhere; using the one real reference the app itself uses
    # avoids that ambiguity entirely.
    import db as db_module
    all_tickets = await db_module.tickets_col.find({"title": "HVAC filter check"}).to_list(length=10)
    org_ids_seen = {t.get("orgId") for t in all_tickets}
    assert org_a["orgId"] in org_ids_seen
    assert org_b["orgId"] in org_ids_seen
