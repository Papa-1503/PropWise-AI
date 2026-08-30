"""
Move-out to deposit-return pipeline (P15).

GET /api/deposit-pipeline/{inspection_id}/preview  -> compute (don't yet
                                                        generate) the full
                                                        itemized breakdown
POST /api/deposit-pipeline/{inspection_id}/generate -> generate the real,
                                                        tenant-facing statement
                                                        document

*** NOT LEGAL ADVICE. This is a simplified, honestly-labeled straight-
line depreciation calculator, not a verified implementation of any
specific jurisdiction's actual security-deposit or HUD depreciation
requirements. *** A genuine search of this repo confirmed the
multi-state HUD depreciation engine referenced in past project history
does not actually exist here - same "described but never committed"
gap this session already found once with on-call/telephony work.
Building a real, jurisdiction-correct depreciation engine responsibly
would mean researching actual HUD life-expectancy tables and each
relevant state's specific security-deposit statute, which is real,
careful legal-research work this pass does not do. This label is
carried through every layer that touches money or a tenant-facing
document - the API response, the generated statement's own text, and
every docstring in this file - not stated once and then dropped.

Real math, straight-line depreciation, matching the general shape HUD
guidance and most state statutes actually use (the SPECIFIC figures -
which useful-life-years number applies to which real item - are
staff-entered per repair_items.usefulLifeYears, not hardcoded here,
since getting those numbers right is exactly the legal-research work
this pass isn't attempting):

  age_years = (now - lease.startDate) in years
    (the lease start date, not a per-fixture install date, is used as
    the "presumed last-good-condition" reference point - a real,
    stated approximation, since no per-fixture install date is
    tracked anywhere in this app)
  remaining_life = max(0, usefulLifeYears - age_years)
  billable_fraction = remaining_life / usefulLifeYears
    (an item already past its useful life has a 0 billable fraction -
    normal wear and tear on something already fully depreciated is
    never billed to the tenant, regardless of its visible condition)
  billable_amount = (part_cost_estimate + labor_cost) * billable_fraction

part_cost_estimate has no real number in this app (P14 deliberately
links to a retailer SEARCH page, not a live price - see
repair_estimates.py) - this pipeline uses only labor_cost in the real
dollar calculation and clearly marks the part cost as "see retailer
link, not included in the total" rather than inventing a placeholder
dollar figure for something this app has no real source for.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends
from bson import ObjectId

from db import inspections_col, leases_col, documents_col, repair_items_col, labor_rates_col
from auth import require_staff
from audit_service import log_action

router = APIRouter(prefix="/api/deposit-pipeline", tags=["deposit-pipeline"])

DISCLAIMER = (
    "This is a computer-generated estimate using a simplified straight-line "
    "depreciation model. It is NOT legal advice and does not guarantee compliance "
    "with any specific state or local security deposit law. Consult your lease "
    "agreement and applicable law, or a qualified professional, before finalizing "
    "any deposit deduction."
)


async def _compute_line_item(item: dict, lease_start: datetime, now: datetime) -> dict | None:
    description = item.get("description", "")
    if not description:
        return None
    repair_item = await repair_items_col.find_one({"damageType": {"$regex": description, "$options": "i"}})
    if not repair_item:
        return {
            "itemId": item.get("id"),
            "description": description,
            "matched": False,
            "note": "No matching repair catalog entry - not included in the billable total.",
        }

    rate_doc = await labor_rates_col.find_one({"category": repair_item["category"]})
    hourly_rate = rate_doc["hourlyRate"] if rate_doc else 0
    labor_cost = repair_item["laborHours"] * hourly_rate

    useful_life = repair_item.get("usefulLifeYears")
    if useful_life and useful_life > 0:
        age_years = (now - lease_start).days / 365.25
        remaining_life = max(0.0, useful_life - age_years)
        billable_fraction = min(1.0, remaining_life / useful_life)
    else:
        billable_fraction = 1.0

    billable_labor = round(labor_cost * billable_fraction, 2)

    return {
        "itemId": item.get("id"),
        "description": description,
        "matched": True,
        "damageType": repair_item["damageType"],
        "partName": repair_item["partName"],
        "partRetailerLink": f"https://www.homedepot.com/s/{repair_item['searchQuery'].replace(' ', '+')}",
        "partCostNote": "See retailer link - not included in this total (no live pricing source).",
        "laborCostFull": round(labor_cost, 2),
        "usefulLifeYears": useful_life,
        "billableFraction": round(billable_fraction, 4),
        "billableLaborAmount": billable_labor,
    }


async def _compute_pipeline(inspection_id: str) -> dict:
    if not ObjectId.is_valid(inspection_id):
        raise HTTPException(status_code=400, detail="Invalid inspection ID")
    inspection = await inspections_col.find_one({"_id": ObjectId(inspection_id)})
    if not inspection:
        raise HTTPException(status_code=404, detail="Inspection not found")
    if inspection.get("type") != "move-out":
        raise HTTPException(status_code=400, detail="This pipeline only applies to move-out inspections.")

    lease = await leases_col.find_one({
        "propertyId": inspection.get("propertyId"), "unitId": inspection.get("unitId"),
    })
    if not lease:
        raise HTTPException(status_code=404, detail="No lease found for this unit to net a deposit against.")

    lease_start = lease.get("startDate")
    if not isinstance(lease_start, datetime):
        raise HTTPException(status_code=400, detail="Lease has no valid start date to compute depreciation from.")
    now = datetime.now(timezone.utc)
    if lease_start.tzinfo is None:
        lease_start = lease_start.replace(tzinfo=timezone.utc)

    flagged_items = [i for i in inspection.get("items", []) if i.get("status") in ("flag", "fail")]
    line_items = []
    for item in flagged_items:
        line = await _compute_line_item(item, lease_start, now)
        if line:
            line_items.append(line)

    total_billable = round(sum(li.get("billableLaborAmount", 0) for li in line_items if li.get("matched")), 2)
    deposit_amount = lease.get("depositAmount", 0)
    final_return_amount = round(deposit_amount - total_billable, 2)

    return {
        "disclaimer": DISCLAIMER,
        "leaseId": str(lease["_id"]),
        "residentName": lease.get("residentName"),
        "unitId": lease.get("unitId"),
        "depositAmount": deposit_amount,
        "lineItems": line_items,
        "totalBillable": total_billable,
        "finalReturnAmount": final_return_amount,
    }


@router.get("/{inspection_id}/preview")
async def preview_deposit_pipeline(inspection_id: str, user: dict = Depends(require_staff)):
    return await _compute_pipeline(inspection_id)


@router.post("/{inspection_id}/generate")
async def generate_deposit_statement(inspection_id: str, user: dict = Depends(require_staff)):
    """Generates the real tenant-facing itemized statement, reusing the
    existing Documents system (documents_col) rather than a separate
    document store - matching P15's own spec. The disclaimer appears
    directly in the generated document's own text, not just this
    endpoint's JSON response, since the document is what a resident
    actually reads."""
    computed = await _compute_pipeline(inspection_id)
    lease = await leases_col.find_one({"_id": ObjectId(computed["leaseId"])})
    if not lease.get("residentEmail"):
        raise HTTPException(status_code=400, detail="Lease has no resident email on file to send this to.")

    lines_text = []
    for li in computed["lineItems"]:
        if li.get("matched"):
            lines_text.append(
                f"- {li['description']}: ${li['billableLaborAmount']:,.2f} labor "
                f"(useful life {li.get('usefulLifeYears', 'n/a')} yrs, "
                f"{li['billableFraction']*100:.0f}% billable after depreciation). "
                f"Part cost not included - see: {li['partRetailerLink']}"
            )
        else:
            lines_text.append(f"- {li['description']}: {li.get('note', 'no catalog match')}")

    content = (
        f"DEPOSIT RETURN STATEMENT — Unit {computed['unitId']}\n\n"
        f"{DISCLAIMER}\n\n"
        f"Resident: {computed['residentName']}\n"
        f"Original deposit: ${computed['depositAmount']:,.2f}\n\n"
        f"Itemized deductions:\n" + "\n".join(lines_text) + "\n\n"
        f"Total billable (labor only, depreciation-adjusted): ${computed['totalBillable']:,.2f}\n"
        f"Final return amount: ${computed['finalReturnAmount']:,.2f}\n"
    )

    doc = {
        "tenantEmail": lease["residentEmail"],
        "leaseId": computed["leaseId"],
        "title": f"Deposit Return Statement - Unit {computed['unitId']}",
        "content": content,
        "documentType": "deposit_statement",
        "status": "sent",
        "signedByName": None,
        "signedAt": None,
        "createdAt": datetime.now(timezone.utc),
    }
    result = await documents_col.insert_one(doc)

    await log_action(
        actor_id=str(user["_id"]), actor_email=user.get("email", ""),
        action="deposit_statement_generated", target_type="lease", target_id=computed["leaseId"],
        details={"finalReturnAmount": computed["finalReturnAmount"], "totalBillable": computed["totalBillable"]},
    )

    return {"documentId": str(result.inserted_id), **computed}
