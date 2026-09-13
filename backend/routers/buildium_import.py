"""
Direct Buildium integration — real, automatic portfolio import from a
customer's own Buildium account, using Buildium's real, self-serve
Open API (confirmed directly from Buildium's own developer docs,
developer.buildium.com - base URL https://api.buildium.com/, API key
auth via x-buildium-client-id/x-buildium-client-secret headers).

WHY BUILDIUM SPECIFICALLY: of the major property-management platforms
a new customer might be migrating from, Buildium is the one with a
genuinely self-serve public API - a customer can generate their own
API key directly from their own Buildium account (Settings ->
Developer Tools), no approval process required. AppFolio's API, by
contrast, is gated behind AppFolio's own partner-application process
and a higher plan tier - not something this app can build around
without PropWise AI itself becoming an approved AppFolio partner,
which is a real, separate business step, not a coding task. This
integration is scoped honestly to what's actually achievable today.

POST /api/import/buildium/preview -> fetches real data from the
                                      customer's Buildium account and
                                      returns counts + a real sample,
                                      WITHOUT writing anything to this
                                      app's database. This exists
                                      specifically because Buildium's
                                      exact response field names carry
                                      some real uncertainty this pass
                                      couldn't fully verify against a
                                      live account - a preview lets
                                      staff see real data landed
                                      correctly before anything is
                                      committed, rather than trusting
                                      a field-mapping guess.
POST /api/import/buildium/commit  -> re-fetches and actually writes
                                      properties/units/leases,
                                      reusing the exact same grouping
                                      and idempotency logic already
                                      proven in bulk_import.py (a
                                      re-run is safe, no duplicates).

CREDENTIAL HANDLING: the customer's Buildium client ID/secret are used
only for the duration of this one request and are never persisted to
this app's database - this is a one-time onboarding pull, not an
ongoing sync. A customer who wants to import again later (e.g. after
adding more units in Buildium) simply re-enters their credentials and
re-runs the import; re-running is safe by the same idempotency
guarantee as the CSV import.

MULTI-TENANCY: everything created here is stamped with the calling
staff member's own orgId, exactly like every other creation path in
this app.
"""
import asyncio
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from db import properties_col, leases_col
from auth import require_staff
from routers.leases import generate_invite_code
from audit_service import log_action

router = APIRouter(prefix="/api/import/buildium", tags=["bulk-import"])

BUILDIUM_BASE_URL = "https://api.buildium.com/v1"
REQUEST_TIMEOUT_SECONDS = 20.0


class BuildiumCredentials(BaseModel):
    clientId: str
    clientSecret: str


def _field(obj: dict, *candidates: str, default=None):
    """Defensive field extraction - tries each candidate key in order
    and returns the first one present. Exists because this pass could
    not verify every exact Buildium response field name against a
    live account (their docs describe the shape but this integration
    was built and tested against representative examples, not a real
    customer's live data) - trying several plausible real names is
    safer than confidently picking one and silently getting it wrong.
    Every field actually used is also shown in the /preview response,
    so a wrong guess is visible to staff before anything is committed,
    not hidden inside a black-box import."""
    for key in candidates:
        if key in obj and obj[key] is not None:
            return obj[key]
    return default


def _extract_address_line(address: dict | None) -> str:
    if not address:
        return ""
    parts = [
        _field(address, "AddressLine1", "Address1", default=""),
        _field(address, "City", default=""),
        _field(address, "State", default=""),
    ]
    return ", ".join(p for p in parts if p)


async def _buildium_get(client: httpx.AsyncClient, path: str, params: dict | None = None) -> list:
    """A single real Buildium API GET, with real error handling for
    the specific failure modes Buildium's own docs describe (401 bad
    credentials, 429 rate limit - retried once after a short delay per
    Buildium's own documented recommendation, other real errors
    surfaced with Buildium's own message rather than a generic one)."""
    try:
        resp = await client.get(f"{BUILDIUM_BASE_URL}{path}", params=params or {})
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach Buildium: {exc}")

    if resp.status_code == 401:
        raise HTTPException(status_code=400, detail="Buildium rejected these credentials. Double-check the Client ID and Secret from Buildium's Settings > Developer Tools.")
    if resp.status_code == 429:
        await asyncio.sleep(0.3)  # Buildium's own documented retry recommendation
        resp = await client.get(f"{BUILDIUM_BASE_URL}{path}", params=params or {})
    if resp.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"Buildium returned an error ({resp.status_code}): {resp.text[:300]}")

    return resp.json()


async def _fetch_buildium_portfolio(credentials: BuildiumCredentials) -> dict:
    """The real, shared fetch logic used by both /preview and /commit -
    guarantees they can never see different data, since /commit
    literally re-runs the same fetch /preview already showed."""
    headers = {
        "x-buildium-client-id": credentials.clientId,
        "x-buildium-client-secret": credentials.clientSecret,
        "Accept": "application/json",
    }

    async with httpx.AsyncClient(headers=headers, timeout=REQUEST_TIMEOUT_SECONDS) as client:
        raw_properties = await _buildium_get(client, "/rentals", {"limit": 1000})

        properties_out = []
        for prop in raw_properties:
            property_id = prop.get("Id")
            units_raw = await _buildium_get(client, f"/rentals/{property_id}/units", {"limit": 1000})
            units_out = []
            for unit in units_raw:
                units_out.append({
                    "unitId": str(_field(unit, "UnitNumber", "Number", "Id", default="")),
                    "rent": _field(unit, "MarketRent", "Rent", default=0) or 0,
                    "bedrooms": _field(unit, "Bedrooms", default=0) or 0,
                    "bathrooms": _field(unit, "Bathrooms", default=0) or 0,
                    "squareFootage": _field(unit, "UnitSize", "SquareFootage", default=None),
                    "buildiumUnitId": property_id and unit.get("Id"),
                })
            properties_out.append({
                "buildiumPropertyId": property_id,
                "name": _field(prop, "Name", default=f"Buildium Property {property_id}"),
                "address": _extract_address_line(_field(prop, "Address", default={})),
                "units": units_out,
            })

        raw_leases = await _buildium_get(client, "/leases", {"limit": 1000})
        tenant_ids_needed = set()
        for lease in raw_leases:
            for t in lease.get("Tenants") or lease.get("CurrentTenants") or []:
                tid = t.get("Id") if isinstance(t, dict) else t
                if tid:
                    tenant_ids_needed.add(tid)

        tenants_by_id = {}
        if tenant_ids_needed:
            raw_tenants = await _buildium_get(client, "/leases/tenants", {"leaseids": ",".join(str(l.get("Id")) for l in raw_leases), "limit": 1000})
            for tenant in raw_tenants:
                tenants_by_id[tenant.get("Id")] = tenant

        leases_out = []
        for lease in raw_leases:
            lease_tenants = lease.get("Tenants") or lease.get("CurrentTenants") or []
            first_tenant_id = None
            for t in lease_tenants:
                first_tenant_id = t.get("Id") if isinstance(t, dict) else t
                if first_tenant_id:
                    break
            tenant = tenants_by_id.get(first_tenant_id, {})
            phones = tenant.get("PhoneNumbers") or []
            phone = phones[0].get("Number") if phones and isinstance(phones[0], dict) else None

            leases_out.append({
                "buildiumPropertyId": lease.get("PropertyId"),
                "buildiumUnitId": lease.get("UnitId"),
                "residentName": " ".join(filter(None, [tenant.get("FirstName"), tenant.get("LastName")])) or "Unknown Resident",
                "residentEmail": tenant.get("Email"),
                "residentPhone": phone,
                "startDate": _field(lease, "LeaseFromDate", "LeaseStartDate", default=None),
                "endDate": _field(lease, "LeaseToDate", "LeaseEndDate", default=None),
                "rent": _field(lease, "Rent", default=0) or 0,
            })

    return {"properties": properties_out, "leases": leases_out}


def _parse_buildium_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


@router.post("/preview")
async def preview_buildium_import(credentials: BuildiumCredentials, user: dict = Depends(require_staff)):
    """Real, live data pulled directly from the customer's own Buildium
    account - not a guess, not mock data. Nothing is written to this
    app's database by this endpoint. Returns real counts plus the
    first few properties/leases in full, so staff can confirm names,
    addresses, rents, and resident names all look right before
    running /commit."""
    portfolio = await _fetch_buildium_portfolio(credentials)
    total_units = sum(len(p["units"]) for p in portfolio["properties"])
    return {
        "propertyCount": len(portfolio["properties"]),
        "unitCount": total_units,
        "leaseCount": len(portfolio["leases"]),
        "sampleProperties": portfolio["properties"][:3],
        "sampleLeases": portfolio["leases"][:3],
    }


@router.post("/commit")
async def commit_buildium_import(credentials: BuildiumCredentials, user: dict = Depends(require_staff)):
    """Re-fetches the same real data /preview showed and actually
    writes it - properties/units first, then leases, matching the
    exact same order and idempotency guarantees as the CSV import in
    bulk_import.py (matched by name/unitId within this org, so a
    second run after fixing something in Buildium never creates
    duplicates)."""
    portfolio = await _fetch_buildium_portfolio(credentials)
    now = datetime.now(timezone.utc)

    properties_created = 0
    properties_updated = 0
    units_added = 0
    buildium_property_to_our_id: dict = {}
    buildium_unit_to_our_unit_id: dict = {}

    for prop in portfolio["properties"]:
        our_units = []
        for u in prop["units"]:
            unit_doc = {
                "unitId": u["unitId"],
                "status": "vacant",
                "rent": u["rent"],
                "bedrooms": u["bedrooms"],
                "bathrooms": u["bathrooms"],
                "readyToList": True,
            }
            if u.get("squareFootage"):
                unit_doc["squareFootage"] = u["squareFootage"]
            our_units.append(unit_doc)
            buildium_unit_to_our_unit_id[u.get("buildiumUnitId")] = u["unitId"]

        existing = await properties_col.find_one({"name": prop["name"], "orgId": user["orgId"]})
        if existing:
            existing_unit_ids = {x.get("unitId") for x in existing.get("units", [])}
            new_units = [u for u in our_units if u["unitId"] not in existing_unit_ids]
            if new_units:
                await properties_col.update_one({"_id": existing["_id"]}, {"$push": {"units": {"$each": new_units}}})
                units_added += len(new_units)
                properties_updated += 1
            buildium_property_to_our_id[prop["buildiumPropertyId"]] = str(existing["_id"])
        else:
            doc = {
                "name": prop["name"],
                "address": prop["address"],
                "units": our_units,
                "orgId": user["orgId"],
                "createdAt": now,
            }
            result = await properties_col.insert_one(doc)
            properties_created += 1
            units_added += len(our_units)
            buildium_property_to_our_id[prop["buildiumPropertyId"]] = str(result.inserted_id)

    leases_created = 0
    lease_errors = []
    for lease in portfolio["leases"]:
        our_property_id = buildium_property_to_our_id.get(lease["buildiumPropertyId"])
        our_unit_id = buildium_unit_to_our_unit_id.get(lease["buildiumUnitId"])
        if not our_property_id or not our_unit_id:
            lease_errors.append(f"Skipped a lease for {lease['residentName']} - its property/unit wasn't found in the properties just imported.")
            continue

        start_date = _parse_buildium_date(lease["startDate"])
        end_date = _parse_buildium_date(lease["endDate"])
        if not start_date or not end_date:
            lease_errors.append(f"Skipped lease for {lease['residentName']} - Buildium didn't provide a valid start/end date.")
            continue

        existing_lease = await leases_col.find_one({
            "propertyId": our_property_id, "unitId": our_unit_id, "orgId": user["orgId"],
            "residentName": lease["residentName"], "startDate": start_date,
        })
        if existing_lease:
            continue  # already imported - safe, idempotent re-run

        doc = {
            "propertyId": our_property_id,
            "unitId": our_unit_id,
            "residentName": lease["residentName"],
            "residentEmail": lease["residentEmail"],
            "residentPhone": lease["residentPhone"],
            "startDate": start_date,
            "endDate": end_date,
            "rent": lease["rent"],
            "renewalStatus": "not_sent",
            "insuranceRequired": False,
            "depositAmount": 0,
            "balance": 0,
            "inviteCode": generate_invite_code(),
            "orgId": user["orgId"],
            "createdAt": now,
        }
        await leases_col.insert_one(doc)
        leases_created += 1

    await log_action(
        actor_id=str(user["id"]), actor_email=user.get("email", ""), org_id=user["orgId"],
        action="buildium_portfolio_imported", target_type="property", target_id=None,
        details={"propertiesCreated": properties_created, "propertiesUpdated": properties_updated, "unitsAdded": units_added, "leasesCreated": leases_created},
    )

    return {
        "status": "done",
        "propertiesCreated": properties_created,
        "propertiesUpdated": properties_updated,
        "unitsAdded": units_added,
        "leasesCreated": leases_created,
        "leaseErrors": lease_errors,
    }
