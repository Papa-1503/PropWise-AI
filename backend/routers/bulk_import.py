"""
Bulk CSV import — the real, missing piece for fast customer onboarding.
Before this, a new organization with an existing portfolio (their own
spreadsheet, or an export from AppFolio/Buildium/etc.) had no way to
get that data into PropWise AI except re-typing every property, unit,
and lease one at a time through the UI. For a customer with 50+ units,
that's real, unacceptable onboarding friction - this closes it.

GET  /api/import/properties/template  -> downloadable CSV template with
                                          the exact expected columns
GET  /api/import/leases/template      -> same, for the leases template
POST /api/import/properties           -> upload a CSV of properties/units
POST /api/import/leases               -> upload a CSV of leases (properties
                                          and units must already exist -
                                          either from the import above, or
                                          created manually)

Deliberately two separate imports, not one combined file: a property
import creates the physical building/unit structure; a lease import
then fills those units with residents. Running properties first, then
leases, mirrors how a real customer's own data is usually organized
(a rent roll spreadsheet often has these as two logically separate
concerns even if stored in one file) and keeps each import's
validation focused and honest about what it actually needs.

REAL, ROW-LEVEL ERROR HANDLING: a bad row never aborts the whole
import or silently vanishes. Every row is validated independently;
successes are committed, and every failure is returned with its
original row number and a real, specific reason - so a staff member
can fix just the bad rows in their spreadsheet and re-run the import,
rather than starting over or wondering what got skipped.

IDEMPOTENT BY DESIGN: re-running the same properties CSV twice does
not create duplicate properties or duplicate units - a property is
matched by name within the org, and a unit is matched by unitId within
that property. This matters in practice: onboarding is rarely a single
clean pass, and a staff member fixing a few bad rows needs to be able
to safely re-upload the same file.

MULTI-TENANCY: every property/unit/lease created here is stamped with
the uploading staff member's own orgId, exactly like every other
creation path in this app - never client-submitted.
"""
import csv
import io
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from fastapi.responses import StreamingResponse
from bson import ObjectId

from db import properties_col, leases_col
from auth import require_staff
from date_utils import parse_date_utc
from routers.leases import generate_invite_code
from audit_service import log_action

router = APIRouter(prefix="/api/import", tags=["bulk-import"])

PROPERTIES_TEMPLATE_COLUMNS = [
    "property_name", "address", "unit_id", "bedrooms", "bathrooms",
    "rent", "square_footage", "status",
]
LEASES_TEMPLATE_COLUMNS = [
    "property_name", "unit_id", "resident_name", "resident_email",
    "resident_phone", "start_date", "end_date", "rent", "deposit_amount",
]


def _csv_template_response(columns: list[str], example_rows: list[list[str]], filename: str) -> StreamingResponse:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(columns)
    for row in example_rows:
        writer.writerow(row)
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/properties/template")
async def download_properties_template(user: dict = Depends(require_staff)):
    """A real, downloadable starting point - not just a list of column
    names in documentation staff would have to retype by hand.
    status is optional (defaults to "vacant" if left blank)."""
    return _csv_template_response(
        PROPERTIES_TEMPLATE_COLUMNS,
        [
            ["Sunset Apartments", "123 Main St, Minneapolis, MN", "101", "2", "1", "1450", "850", "occupied"],
            ["Sunset Apartments", "123 Main St, Minneapolis, MN", "102", "1", "1", "1100", "600", "vacant"],
        ],
        "propwise_properties_template.csv",
    )


@router.get("/leases/template")
async def download_leases_template(user: dict = Depends(require_staff)):
    """property_name and unit_id here must exactly match a property/
    unit that already exists (either imported above, or created
    manually) - this import fills units with residents, it does not
    create new units on the fly."""
    return _csv_template_response(
        LEASES_TEMPLATE_COLUMNS,
        [
            ["Sunset Apartments", "101", "Jane Doe", "jane@example.com", "612-555-0100", "2026-01-01", "2026-12-31", "1450", "1450"],
        ],
        "propwise_leases_template.csv",
    )


def _parse_float(value: str, field: str, row_num: int) -> float:
    value = (value or "").strip()
    if not value:
        return 0.0
    try:
        return float(value)
    except ValueError:
        raise ValueError(f"Row {row_num}: '{field}' must be a number, got '{value}'")


def _parse_int(value: str, field: str, row_num: int) -> int:
    value = (value or "").strip()
    if not value:
        return 0
    try:
        return int(float(value))
    except ValueError:
        raise ValueError(f"Row {row_num}: '{field}' must be a whole number, got '{value}'")


@router.post("/properties")
async def import_properties(file: UploadFile = File(...), user: dict = Depends(require_staff)):
    """Groups rows by property_name (case-sensitive exact match) - every
    row sharing the same property_name becomes a unit under ONE
    property document, matching this app's existing embedded-units
    data model (see PropertyCreate/UnitIn in models.py). If a property
    with that exact name already exists in this org, new units are
    ADDED to it rather than creating a duplicate property - this is
    what makes re-running the same file after fixing a few bad rows
    safe."""
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a .csv file.")

    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")  # handles a leading BOM from Excel exports, a real, common gotcha
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="Could not read this file as UTF-8 text. Please export your spreadsheet as CSV (UTF-8).")

    reader = csv.DictReader(io.StringIO(text))
    missing_columns = set(["property_name", "address", "unit_id"]) - set(reader.fieldnames or [])
    if missing_columns:
        raise HTTPException(status_code=400, detail=f"Missing required column(s): {', '.join(sorted(missing_columns))}. Download the template to see the expected format.")

    errors: list[str] = []
    # Real, in-memory grouping before touching the database - property_name -> list of validated unit dicts
    grouped: dict[str, dict] = {}

    for row_num, row in enumerate(reader, start=2):  # start=2: row 1 is the header, so the first data row is "row 2" - matches what a person sees if they open the file in a spreadsheet app
        property_name = (row.get("property_name") or "").strip()
        address = (row.get("address") or "").strip()
        unit_id = (row.get("unit_id") or "").strip()
        if not property_name or not unit_id:
            errors.append(f"Row {row_num}: property_name and unit_id are both required - skipped.")
            continue
        try:
            unit = {
                "unitId": unit_id,
                "status": (row.get("status") or "vacant").strip() or "vacant",
                "rent": _parse_float(row.get("rent"), "rent", row_num),
                "bedrooms": _parse_int(row.get("bedrooms"), "bedrooms", row_num),
                "bathrooms": _parse_float(row.get("bathrooms"), "bathrooms", row_num),
                "readyToList": True,
            }
            sqft = _parse_float(row.get("square_footage"), "square_footage", row_num)
            if sqft:
                unit["squareFootage"] = sqft
        except ValueError as exc:
            errors.append(str(exc))
            continue

        if unit["status"] not in ("occupied", "vacant", "maintenance_hold"):
            errors.append(f"Row {row_num}: status must be 'occupied', 'vacant', or 'maintenance_hold' - got '{unit['status']}'. Skipped.")
            continue

        if property_name not in grouped:
            grouped[property_name] = {"address": address, "units": []}
        grouped[property_name]["units"].append(unit)

    properties_created = 0
    properties_updated = 0
    units_added = 0
    now = datetime.now(timezone.utc)

    for property_name, data in grouped.items():
        existing = await properties_col.find_one({"name": property_name, "orgId": user["orgId"]})
        if existing:
            existing_unit_ids = {u.get("unitId") for u in existing.get("units", [])}
            new_units = [u for u in data["units"] if u["unitId"] not in existing_unit_ids]
            skipped_duplicate_units = len(data["units"]) - len(new_units)
            if skipped_duplicate_units:
                errors.append(f"Property '{property_name}': {skipped_duplicate_units} unit(s) already existed and were left unchanged (re-run is safe, duplicates are never created).")
            if new_units:
                await properties_col.update_one({"_id": existing["_id"]}, {"$push": {"units": {"$each": new_units}}})
                units_added += len(new_units)
                properties_updated += 1
        else:
            doc = {
                "name": property_name,
                "address": data["address"],
                "units": data["units"],
                "orgId": user["orgId"],
                "createdAt": now,
            }
            await properties_col.insert_one(doc)
            properties_created += 1
            units_added += len(data["units"])

    await log_action(
        actor_id=str(user["id"]), actor_email=user.get("email", ""), org_id=user["orgId"],
        action="bulk_properties_imported", target_type="property", target_id=None,
        details={"propertiesCreated": properties_created, "propertiesUpdated": properties_updated, "unitsAdded": units_added, "errorCount": len(errors)},
    )

    return {
        "status": "done",
        "propertiesCreated": properties_created,
        "propertiesUpdated": properties_updated,
        "unitsAdded": units_added,
        "errors": errors,
    }


@router.post("/leases")
async def import_leases(file: UploadFile = File(...), user: dict = Depends(require_staff)):
    """Each row must reference a property_name and unit_id that already
    exist in this org (from the properties import above, or created
    manually) - this endpoint fills existing units with residents, it
    never creates new units on the fly, so a typo in unit_id fails
    that row with a clear reason rather than silently creating a
    phantom unit no property actually has."""
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a .csv file.")

    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="Could not read this file as UTF-8 text. Please export your spreadsheet as CSV (UTF-8).")

    reader = csv.DictReader(io.StringIO(text))
    required = {"property_name", "unit_id", "resident_name", "start_date", "end_date"}
    missing_columns = required - set(reader.fieldnames or [])
    if missing_columns:
        raise HTTPException(status_code=400, detail=f"Missing required column(s): {', '.join(sorted(missing_columns))}. Download the template to see the expected format.")

    errors: list[str] = []
    leases_created = 0
    now = datetime.now(timezone.utc)
    # Cache property lookups within this one import run - a real,
    # simple optimization for a file with many rows against the same
    # handful of properties, not a correctness requirement.
    property_cache: dict[str, dict | None] = {}

    for row_num, row in enumerate(reader, start=2):
        property_name = (row.get("property_name") or "").strip()
        unit_id = (row.get("unit_id") or "").strip()
        resident_name = (row.get("resident_name") or "").strip()
        start_date_raw = (row.get("start_date") or "").strip()
        end_date_raw = (row.get("end_date") or "").strip()

        if not (property_name and unit_id and resident_name and start_date_raw and end_date_raw):
            errors.append(f"Row {row_num}: property_name, unit_id, resident_name, start_date, and end_date are all required - skipped.")
            continue

        if property_name not in property_cache:
            property_cache[property_name] = await properties_col.find_one({"name": property_name, "orgId": user["orgId"]})
        property_doc = property_cache[property_name]
        if not property_doc:
            errors.append(f"Row {row_num}: no property named '{property_name}' found - import properties first, or check for a typo.")
            continue

        unit_exists = any(u.get("unitId") == unit_id for u in property_doc.get("units", []))
        if not unit_exists:
            errors.append(f"Row {row_num}: property '{property_name}' has no unit '{unit_id}' - check for a typo.")
            continue

        try:
            start_date = parse_date_utc(start_date_raw)
            end_date = parse_date_utc(end_date_raw)
        except HTTPException as exc:
            errors.append(f"Row {row_num}: {exc.detail}")
            continue

        try:
            rent = _parse_float(row.get("rent"), "rent", row_num)
            deposit_amount = _parse_float(row.get("deposit_amount"), "deposit_amount", row_num)
        except ValueError as exc:
            errors.append(str(exc))
            continue

        existing_lease = await leases_col.find_one({
            "propertyId": str(property_doc["_id"]), "unitId": unit_id, "orgId": user["orgId"],
            "residentName": resident_name, "startDate": start_date,
        })
        if existing_lease:
            errors.append(f"Row {row_num}: a lease for {resident_name} in unit {unit_id} starting {start_date_raw} already exists - skipped (re-run is safe, duplicates are never created).")
            continue

        doc = {
            "propertyId": str(property_doc["_id"]),
            "unitId": unit_id,
            "residentName": resident_name,
            "residentEmail": (row.get("resident_email") or "").strip() or None,
            "residentPhone": (row.get("resident_phone") or "").strip() or None,
            "startDate": start_date,
            "endDate": end_date,
            "rent": rent,
            "renewalStatus": "not_sent",
            "insuranceRequired": False,
            "depositAmount": deposit_amount,
            "balance": 0,
            "inviteCode": generate_invite_code(),
            "orgId": user["orgId"],
            "createdAt": now,
        }
        await leases_col.insert_one(doc)
        leases_created += 1

    await log_action(
        actor_id=str(user["id"]), actor_email=user.get("email", ""), org_id=user["orgId"],
        action="bulk_leases_imported", target_type="lease", target_id=None,
        details={"leasesCreated": leases_created, "errorCount": len(errors)},
    )

    return {
        "status": "done",
        "leasesCreated": leases_created,
        "errors": errors,
    }
