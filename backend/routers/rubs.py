"""
RUBS — Ratio Utility Billing System.

POST /api/rubs/preview   -> compute (don't yet charge) the real
                             per-unit allocation for a utility bill
POST /api/rubs/generate  -> compute AND create real per-unit charges
                             in the existing payments ledger

Only allocates across OCCUPIED units - a vacant unit has no resident
to bill, and including it in the allocation base would either
overcharge occupied residents (if vacant units are excluded from the
total but somehow still divide it) or bill nobody for a vacant unit's
share (silently absorbed as a loss with no visibility) - this always
divides only among the units that actually have someone to charge.

Real, honest allocation methods, not a single default that's rarely
what a property actually wants:
  - squareFootage: each unit's share = its own sqft / total occupied
    sqft. Requires squareFootage to actually be set on occupied units;
    any occupied unit missing it is a real gap that would silently
    skew the allocation - reported explicitly, not hidden.
  - bedroomCount: same math, using each unit's real bedrooms field
    (already existed before this feature).
  - equalSplit: total / number of occupied units. Needs no per-unit
    data at all - the honest fallback for a property that hasn't
    recorded square footage.

MULTI-TENANCY: real ownership check on the property before any
allocation is computed or any charge is created - see
_compute_allocation's own comment for why this matters here
specifically (propertyId comes straight from the request body).
Generated charges carry a real orgId, stamped from the requesting
staff member.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends
from bson import ObjectId

from db import properties_col, payments_col
from models import RubsBillCreate
from date_utils import parse_date_utc
from auth import require_staff
from audit_service import log_action

router = APIRouter(prefix="/api/rubs", tags=["rubs"])


async def _compute_allocation(payload: RubsBillCreate, org_id: str) -> dict:
    # Real ownership check, not just scoping: propertyId comes straight
    # from the request body, so without this a staff member could
    # allocate - and via /generate, actually CHARGE - a different
    # organization's property simply by supplying its real property ID.
    query_id = ObjectId(payload.propertyId) if ObjectId.is_valid(payload.propertyId) else payload.propertyId
    property_doc = await properties_col.find_one({"_id": query_id, "orgId": org_id})
    if not property_doc:
        raise HTTPException(status_code=404, detail="Property not found")

    occupied_units = [u for u in property_doc.get("units", []) if u.get("status") == "occupied"]
    if not occupied_units:
        raise HTTPException(status_code=400, detail="No occupied units to allocate this bill across.")

    warnings = []
    if payload.allocationMethod == "equalSplit":
        share = round(payload.totalAmount / len(occupied_units), 2)
        allocations = [{"unitId": u["unitId"], "amount": share, "basis": "1 (equal share)"} for u in occupied_units]

    elif payload.allocationMethod in ("squareFootage", "bedroomCount"):
        basis_field = "squareFootage" if payload.allocationMethod == "squareFootage" else "bedrooms"
        missing_basis = [u["unitId"] for u in occupied_units if not u.get(basis_field)]
        if missing_basis:
            warnings.append(
                f"{len(missing_basis)} occupied unit(s) have no {basis_field} on file "
                f"({', '.join(missing_basis)}) - they were excluded from this allocation, "
                f"NOT charged $0. Set {basis_field} for them and re-run, or use equalSplit instead."
            )
        eligible_units = [u for u in occupied_units if u.get(basis_field)]
        if not eligible_units:
            raise HTTPException(status_code=400, detail=f"No occupied units have {basis_field} on file to allocate by.")

        total_basis = sum(u[basis_field] for u in eligible_units)
        allocations = []
        running_total = 0.0
        for u in eligible_units:
            share = round(payload.totalAmount * (u[basis_field] / total_basis), 2)
            running_total += share
            allocations.append({"unitId": u["unitId"], "amount": share, "basis": f"{u[basis_field]} {basis_field}"})
        rounding_diff = round(payload.totalAmount - running_total, 2)
        if abs(rounding_diff) >= 0.01:
            warnings.append(f"Allocated total (${running_total:,.2f}) differs from bill total by ${rounding_diff:,.2f} due to per-unit rounding.")

    return {
        "propertyId": payload.propertyId,
        "utilityType": payload.utilityType,
        "totalAmount": payload.totalAmount,
        "billingPeriod": payload.billingPeriod,
        "allocationMethod": payload.allocationMethod,
        "allocations": allocations,
        "warnings": warnings,
    }


@router.post("/preview")
async def preview_rubs_bill(payload: RubsBillCreate, user: dict = Depends(require_staff)):
    return await _compute_allocation(payload, user["orgId"])


@router.post("/generate")
async def generate_rubs_charges(payload: RubsBillCreate, user: dict = Depends(require_staff)):
    """Computes the allocation (same logic as /preview) AND actually
    creates a real charge per unit in payments_col, reusing the exact
    same document shape ChargeCreate produces - a RUBS charge is a
    real charge in the same ledger as rent, not a separate, siloed
    utility-billing system a resident would need to check somewhere
    else."""
    computed = await _compute_allocation(payload, user["orgId"])
    due_date = parse_date_utc(payload.dueDate)
    now = datetime.now(timezone.utc)

    created_ids = []
    for alloc in computed["allocations"]:
        doc = {
            "propertyId": payload.propertyId,
            "unitId": alloc["unitId"],
            "orgId": user["orgId"],
            "leaseId": None,
            "amountDue": alloc["amount"],
            "amountPaid": 0.0,
            "paidDate": None,
            "dueDate": due_date,
            "description": f"{payload.utilityType.title()} ({payload.billingPeriod}) - RUBS, {alloc['basis']}",
            "createdAt": now,
        }
        result = await payments_col.insert_one(doc)
        created_ids.append(str(result.inserted_id))

    await log_action(
        actor_id=str(user["id"]), actor_email=user.get("email", ""),
        action="rubs_bill_generated", target_type="property", target_id=payload.propertyId,
        details={"utilityType": payload.utilityType, "totalAmount": payload.totalAmount, "chargeCount": len(created_ids)},
    )

    return {**computed, "chargesCreated": len(created_ids), "chargeIds": created_ids}
