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

from db import inspections_col, leases_col, documents_col, repair_items_col, labor_rates_col, photos_col
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

    # Real photo documentation for THIS specific item, not just any
    # unit photo - genuinely required by real photo-documentation
    # rules like California's AB 2801 (amends Civil Code §1950.5,
    # confirmed directly against real, current sources - move-in,
    # move-out, and post-repair photos tied to the specific deduction,
    # not a generic requirement). Only includes photos with a real
    # itemId match to this exact flagged item - a general unit photo
    # with no itemId set doesn't count as documentation for a specific
    # deduction, and shouldn't be misrepresented as such.
    item_photos = await photos_col.find({"itemId": item.get("id")}).to_list(length=20)
    photo_urls = [p["url"] for p in item_photos]

    repair_item = await repair_items_col.find_one({"damageType": {"$regex": description, "$options": "i"}})
    if not repair_item:
        return {
            "itemId": item.get("id"),
            "description": description,
            "matched": False,
            "note": "No matching repair catalog entry - not included in the billable total.",
            "photoUrls": photo_urls,
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
        "photoUrls": photo_urls,
        "photoDocumented": len(photo_urls) > 0,
        # ^ A real, honest flag - whether this specific deduction has
        # at least one real photo tied to it. Deliberately does NOT
        # claim this satisfies any specific state's actual photo-
        # documentation statute (which state, which exact timing
        # requirements, etc. is real legal-research work this session
        # explicitly isn't attempting) - just states the real,
        # verifiable fact of whether documentation exists, which staff
        # and any real compliance review can act on themselves.
    }


async def _compute_pipeline(inspection_id: str, org_id: str) -> dict:
    if not ObjectId.is_valid(inspection_id):
        raise HTTPException(status_code=400, detail="Invalid inspection ID")
    inspection = await inspections_col.find_one({"_id": ObjectId(inspection_id), "orgId": org_id})
    if not inspection:
        raise HTTPException(status_code=404, detail="Inspection not found")
    if inspection.get("type") != "move-out":
        raise HTTPException(status_code=400, detail="This pipeline only applies to move-out inspections.")

    lease = await leases_col.find_one({
        "propertyId": inspection.get("propertyId"), "unitId": inspection.get("unitId"), "orgId": org_id,
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

    undocumented_billable = [
        li["description"] for li in line_items
        if li.get("matched") and li.get("billableLaborAmount", 0) > 0 and not li.get("photoDocumented")
    ]
    photo_warning = None
    if undocumented_billable:
        # A real, actionable flag for staff - never a compliance
        # claim about any specific state's actual photo-documentation
        # law (which this pass explicitly doesn't research or
        # enforce), just an honest fact: these billable deductions
        # have no photo attached in this app, which several real
        # states' recent laws (e.g. California's AB 2801) require for
        # a deduction to be defensible.
        photo_warning = (
            f"{len(undocumented_billable)} billable item(s) have no photo documentation on file: "
            + ", ".join(undocumented_billable) +
            ". Several states now require photo documentation to support a deposit deduction - "
            "check your applicable law before finalizing."
        )

    return {
        "disclaimer": DISCLAIMER,
        "leaseId": str(lease["_id"]),
        "residentName": lease.get("residentName"),
        "unitId": lease.get("unitId"),
        "depositAmount": deposit_amount,
        "lineItems": line_items,
        "totalBillable": total_billable,
        "finalReturnAmount": final_return_amount,
        "photoDocumentationWarning": photo_warning,
    }


@router.get("/{inspection_id}/preview")
async def preview_deposit_pipeline(inspection_id: str, user: dict = Depends(require_staff)):
    return await _compute_pipeline(inspection_id, user["orgId"])


async def _do_generate_deposit_statement(inspection_id: str, actor_id: str, actor_email: str, status: str, org_id: str) -> dict:
    """The actual generation logic, split out so it can be called two
    ways: the existing manual endpoint below (status="sent", staff
    explicitly generating AND sending in one deliberate action, exactly
    as it already worked), and the new automatic trigger in
    inspections.py (status="draft", the moment a move-out inspection's
    last item is resolved).

    Deliberately NOT auto-SENDING — a draft still needs a real staff
    action (POST /{document_id}/finalize below) before a resident ever
    sees it. Deposit deductions carry genuine financial and legal
    stakes (most states have strict security-deposit itemization/timing
    requirements); removing the human checkpoint entirely, not just the
    manual data-entry work, would trade a real safeguard for convenience
    this feature was never asked to give up."""
    computed = await _compute_pipeline(inspection_id, org_id)
    lease = await leases_col.find_one({"_id": ObjectId(computed["leaseId"])})
    if not lease.get("residentEmail"):
        raise HTTPException(status_code=400, detail="Lease has no resident email on file to send this to.")

    lines_text = []
    for li in computed["lineItems"]:
        if li.get("matched"):
            photo_note = (
                f" Photos on file: {len(li['photoUrls'])} - " + ", ".join(li["photoUrls"])
                if li.get("photoDocumented")
                else " No photos on file for this specific item."
            )
            lines_text.append(
                f"- {li['description']}: ${li['billableLaborAmount']:,.2f} labor "
                f"(useful life {li.get('usefulLifeYears', 'n/a')} yrs, "
                f"{li['billableFraction']*100:.0f}% billable after depreciation). "
                f"Part cost not included - see: {li['partRetailerLink']}.{photo_note}"
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
    if status == "draft":
        content = (
            "*** DRAFT — auto-generated, not yet reviewed or sent to the resident. "
            "A staff member must finalize this before it goes out. ***\n\n" + content
        )

    doc = {
        "tenantEmail": lease["residentEmail"],
        "leaseId": computed["leaseId"],
        "orgId": org_id,
        "inspectionId": inspection_id,
        "title": f"Deposit Return Statement - Unit {computed['unitId']}",
        "content": content,
        "documentType": "deposit_statement",
        "status": status,
        "signedByName": None,
        "signedAt": None,
        "createdAt": datetime.now(timezone.utc),
    }
    result = await documents_col.insert_one(doc)

    await log_action(
        actor_id=actor_id, actor_email=actor_email,
        action="deposit_statement_generated" if status == "sent" else "deposit_statement_draft_auto_generated",
        target_type="lease", target_id=computed["leaseId"],
        details={"finalReturnAmount": computed["finalReturnAmount"], "totalBillable": computed["totalBillable"], "status": status},
    )

    return {"documentId": str(result.inserted_id), **computed}


async def has_existing_deposit_statement(inspection_id: str) -> bool:
    """Guards the auto-generation trigger against creating a duplicate
    draft if an inspection's items get edited again after every item
    was already resolved once."""
    existing = await documents_col.find_one({"inspectionId": inspection_id, "documentType": "deposit_statement"})
    return existing is not None


async def maybe_auto_generate_deposit_draft(inspection_id: str, org_id: str) -> None:
    """Called from inspections.py after any item status update. Checks
    whether THIS update was the one that resolved the last pending item
    on a move-out inspection, and if so, auto-generates a draft deposit
    statement — genuinely reducing the manual work (a staff member no
    longer has to remember to go run this), while keeping a real human
    checkpoint (see _do_generate_deposit_statement's own docstring)
    before anything reaches a resident. Fails silently on any error
    (e.g. no lease found, no resident email on file) rather than
    blocking the item-status update itself — the inspection update is
    the real action being performed here; a failed auto-draft attempt
    is a missed convenience, not a reason to break the actual request.
    org_id comes from the staff member updating the inspection item -
    inspections.py already verified that inspection belongs to their
    own org before this is ever called."""
    if not ObjectId.is_valid(inspection_id):
        return
    inspection = await inspections_col.find_one({"_id": ObjectId(inspection_id), "orgId": org_id})
    if not inspection or inspection.get("type") != "move-out":
        return
    items = inspection.get("items", [])
    if not items or any(i.get("status") == "pending" for i in items):
        return  # not every item resolved yet
    if await has_existing_deposit_statement(inspection_id):
        return  # already generated once, don't duplicate

    try:
        await _do_generate_deposit_statement(
            inspection_id, actor_id="system_auto_generate", actor_email="", status="draft", org_id=org_id,
        )
    except Exception as e:
        print(f"Auto deposit-statement draft generation failed for inspection {inspection_id}: {e}")


@router.post("/{inspection_id}/generate")
async def generate_deposit_statement(inspection_id: str, user: dict = Depends(require_staff)):
    """Generates the real tenant-facing itemized statement, reusing the
    existing Documents system (documents_col) rather than a separate
    document store - matching P15's own spec. The disclaimer appears
    directly in the generated document's own text, not just this
    endpoint's JSON response, since the document is what a resident
    actually reads. Unchanged behavior — an explicit staff-triggered
    call still generates AND marks it sent in one deliberate action,
    exactly as before; the new draft/finalize flow only applies to the
    automatic trigger in inspections.py."""
    return await _do_generate_deposit_statement(
        inspection_id, actor_id=str(user["id"]), actor_email=user.get("email", ""), status="sent", org_id=user["orgId"],
    )


@router.post("/statements/{document_id}/finalize")
async def finalize_deposit_statement(document_id: str, user: dict = Depends(require_staff)):
    """The real human checkpoint for an auto-generated draft — a staff
    member reviews the computed amounts (via the draft document's own
    content, or GET /{inspection_id}/preview for the same numbers) and
    explicitly finalizes it before it's considered sent. Only valid on
    a document that's actually still a draft — finalizing an
    already-sent statement, or a document that was never a deposit
    statement at all, is rejected rather than silently accepted."""
    if not ObjectId.is_valid(document_id):
        raise HTTPException(status_code=400, detail="Invalid document ID")
    doc = await documents_col.find_one({"_id": ObjectId(document_id), "orgId": user["orgId"]})
    if not doc or doc.get("documentType") != "deposit_statement":
        raise HTTPException(status_code=404, detail="Deposit statement not found")
    if doc.get("status") != "draft":
        raise HTTPException(status_code=400, detail=f"This statement is already '{doc.get('status')}', not a draft.")

    # Strip the draft banner this specific document was created with,
    # so the finalized version reads exactly like one generated
    # directly via the manual endpoint — no leftover "not yet reviewed"
    # language on something a staff member just explicitly reviewed.
    cleaned_content = doc["content"].split("***\n\n", 1)[-1] if doc["content"].startswith("*** DRAFT") else doc["content"]

    result = await documents_col.find_one_and_update(
        {"_id": ObjectId(document_id)},
        {"$set": {"status": "sent", "content": cleaned_content, "finalizedAt": datetime.now(timezone.utc), "finalizedBy": user.get("email")}},
        return_document=True,
    )

    await log_action(
        actor_id=str(user["id"]), actor_email=user.get("email", ""),
        action="deposit_statement_finalized", target_type="lease", target_id=doc.get("leaseId"),
        details={},
    )

    result["id"] = str(result.pop("_id"))
    return result
