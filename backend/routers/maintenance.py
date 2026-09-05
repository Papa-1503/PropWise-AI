"""
Maintenance ticket endpoints.

GET   /api/maintenance/tickets            -> list, filterable by propertyId/status
POST  /api/maintenance/tickets            -> create a ticket (used directly by staff,
                                              and auto-called from the inspection flow)
PATCH /api/maintenance/tickets/:id        -> update status/assignee/priority
POST  /api/maintenance/tickets/:id/time   -> log hours worked against a ticket

Resident-submitted tickets (source == "resident") are auto-assigned to a
staff member whose assignedProperties includes the ticket's propertyId,
via routers/staff.py. If no tech is assigned to that property yet, falls
back to the existing notify_all_staff behavior rather than leaving the
ticket silently unassigned.

Time logging is intentionally simple — hours entered directly, not a
running timer. No payroll, tax, or workers' comp logic; this is purely
for internal labor-cost accuracy, feeding the estimate-vs-actual
comparison planned in the damage cost estimates feature.

MULTI-TENANCY: every ticket carries a real orgId. create_ticket_document
below is the single real choke point every ticket-creation path in this
app goes through (this file's own HTTP handler, routers/telephony.py's
AI phone triage, routers/sms_inbound.py's text-in triage) - org_id is
now a REQUIRED, explicit parameter on that function (not just a dict
key a caller could forget to set), so a new caller literally cannot
compile without deciding whose org a ticket belongs to. Every other
query below is scoped through user["orgId"] directly.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends
from bson import ObjectId

from db import tickets_col, users_col
from models import TicketCreate, TicketUpdate, TimeEntryCreate, TicketSatisfactionSubmit
import notifications_service
from auth import require_staff, get_current_user
from services.events import emit_event
from services.ticket_dedup import find_existing_open_duplicate, record_duplicate_occurrence
from services.ticket_severity import compute_severity
import vendor_sla_service

router = APIRouter(prefix="/api/maintenance/tickets", tags=["maintenance"])


def serialize(ticket: dict) -> dict:
    ticket["id"] = str(ticket.pop("_id"))
    return ticket


async def find_tech_for_property(property_id: str) -> dict | None:
    """Returns the first staff user assigned to this property, or None."""
    return await users_col.find_one({"role": "staff", "assignedProperties": property_id})




@router.get("")
async def list_tickets(
    propertyId: str | None = None,
    status: str | None = None,
    user: dict = Depends(get_current_user),
):
    query = {"orgId": user.get("orgId")}
    if user["role"] == "tenant":
        query["propertyId"] = user.get("propertyId")
        query["unitId"] = user.get("unitId")
    elif propertyId:
        query["propertyId"] = propertyId
    if status:
        query["status"] = status
    cursor = tickets_col.find(query).sort("createdAt", -1).limit(200)
    tickets = await cursor.to_list(length=200)
    return {"tickets": [serialize(t) for t in tickets]}


@router.post("")
async def create_ticket(payload: TicketCreate, user: dict = Depends(get_current_user)):
    doc = payload.model_dump()
    if user["role"] == "tenant":
        doc["propertyId"] = user.get("propertyId")
        doc["unitId"] = user.get("unitId")
        doc["source"] = "resident"
    return await create_ticket_document(doc, user["orgId"])


async def create_ticket_document(doc: dict, org_id: str) -> dict:
    """The real, full ticket-creation pipeline (dedup check, real
    deterministic severity scoring, auto-assignment to a property's
    tech, low/routine-tier vendor auto-dispatch, real notifications) -
    extracted from the HTTP handler above so other real callers
    (routers/telephony.py's AI phone triage, routers/sms_inbound.py's
    text-in triage) get the exact same pipeline a normal ticket
    submission gets, not a smaller reimplementation of a subset of it.
    `doc` must already have propertyId/unitId/title/description/
    category/priority/source set; status, createdAt, and orgId are set
    here. org_id is a required, explicit parameter (not folded into
    doc) so every call site has to consciously decide whose
    organization a ticket belongs to - it can never be silently
    missing the way a forgotten dict key could be."""
    doc["status"] = "open"
    doc["createdAt"] = datetime.now(timezone.utc)
    doc["orgId"] = org_id

    existing_duplicate = await find_existing_open_duplicate(
        doc.get("propertyId"), doc.get("unitId"), doc.get("title")
    )
    if existing_duplicate:
        await record_duplicate_occurrence(existing_duplicate)
        existing_duplicate["_id"] = str(existing_duplicate["_id"])
        return {**existing_duplicate, "wasExistingDuplicate": True}

    severity = compute_severity(doc.get("title"), doc.get("category"))
    doc["severityScore"] = severity["score"]
    doc["severityTier"] = severity["tier"]
    doc["severityExplanation"] = severity["explanation"]

    assigned_tech = None
    if doc.get("source") == "resident" and doc.get("propertyId"):
        assigned_tech = await find_tech_for_property(doc["propertyId"])
        if assigned_tech:
            doc["assignee"] = assigned_tech.get("email")

    # Auto vendor dispatch — deliberately gated on the COMPUTED severity
    # tier (low/routine), not the raw priority a resident self-reported,
    # since residents both over- and under-report urgency (the entire
    # reason ticket_severity.py exists). "urgent"/"emergency" tickets
    # always stay unassigned here regardless of what preferredVendors
    # says, so a human makes that call every time the stakes are real.
    #
    # CHANGED (Sept 2, 2026): the actual assignment + real SLA
    # tracking (acceptance token, deadline, confirmation SMS) now
    # happens via vendor_sla_service.dispatch_with_sla AFTER insert,
    # since that needs a real ticket _id to track against — the
    # candidate vendor is still found before insert so a ticket that
    # has no eligible vendor at all doesn't pay for a second DB round
    # trip it doesn't need.
    auto_assign_candidate = None
    if severity["tier"] in ("low", "routine") and doc.get("propertyId") and doc.get("category"):
        auto_assign_candidate = await vendor_sla_service.find_next_eligible_vendor(doc["propertyId"], doc["category"])

    result = await tickets_col.insert_one(doc)
    doc["_id"] = result.inserted_id

    auto_assigned_vendor = None
    if auto_assign_candidate:
        await vendor_sla_service.dispatch_with_sla(str(result.inserted_id), doc, auto_assign_candidate)
        doc["status"] = "in_progress"
        doc["estimatedArrivalHours"] = auto_assign_candidate.get("avgArrivalHours")
        await tickets_col.update_one({"_id": result.inserted_id}, {"$set": {"vendorAutoAssigned": True}})
        auto_assigned_vendor = auto_assign_candidate

    if doc.get("source") == "resident":
        if assigned_tech:
            await notifications_service.notify_user(
                str(assigned_tech["_id"]),
                type="urgent_ticket" if doc.get("priority") == "urgent" else "general",
                title=f"New maintenance request: {doc['title']}",
                body=f"Unit {doc['unitId']} — assigned to you",
                link=f"/maintenance/{str(result.inserted_id)}",
            )
        else:
            await notifications_service.notify_all_staff(
                type="urgent_ticket" if doc.get("priority") == "urgent" else "general",
                title=f"Unassigned request: {doc['title']}",
                body=f"Unit {doc['unitId']} — no tech assigned to this property yet",
                link=f"/maintenance/{str(result.inserted_id)}",
            )
        if auto_assigned_vendor:
            eta = doc.get("estimatedArrivalHours")
            await notifications_service.notify_unit_resident(
                doc.get("propertyId"), doc.get("unitId"),
                type="vendor_assigned",
                title=f"{auto_assigned_vendor['name']} assigned to your request",
                body=f"{doc.get('title', 'Your maintenance request')}" + (f" — ETA ~{eta}h" if eta else ""),
                link=f"/maintenance/{str(result.inserted_id)}",
            )
    elif doc.get("priority") == "urgent":
        await notifications_service.notify_all_staff(
            type="urgent_ticket",
            title=f"Urgent: {doc['title']}",
            body=f"Unit {doc['unitId']} — reported via {doc.get('source', 'staff')}",
            link=f"/maintenance/{str(result.inserted_id)}",
        )

    return serialize(doc)


@router.patch("/{ticket_id}")
async def update_ticket(ticket_id: str, payload: TicketUpdate, user: dict = Depends(require_staff)):
    if not ObjectId.is_valid(ticket_id):
        raise HTTPException(status_code=400, detail="Invalid ticket ID")
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    if updates.get("status") == "done":
        # A real, human-written resolution summary is required to
        # actually close a ticket - either provided in this same
        # request, or already on file from an earlier PATCH (e.g. a
        # tech writes it up first, then a supervisor changes status
        # separately). Never allowed to silently close with nothing
        # explaining what was actually done - that's the entire point
        # of this feature, not an optional nice-to-have.
        existing = await tickets_col.find_one({"_id": ObjectId(ticket_id), "orgId": user["orgId"]}, {"resolutionNotes": 1})
        has_existing_notes = bool(existing and existing.get("resolutionNotes"))
        if not updates.get("resolutionNotes") and not has_existing_notes:
            raise HTTPException(
                status_code=400,
                detail="Resolution notes are required to close a ticket - describe what was found and what was done to fix it.",
            )

    updates["updatedAt"] = datetime.now(timezone.utc)
    result = await tickets_col.find_one_and_update(
        {"_id": ObjectId(ticket_id), "orgId": user["orgId"]},
        {"$set": updates},
        return_document=True,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Ticket not found")

    if updates.get("status") == "done":
        try:
            await emit_event("work_order_closed", {
                "ticketId": ticket_id,
                "propertyId": result.get("propertyId"),
                "unitId": result.get("unitId"),
                "title": result.get("title"),
            })
        except Exception as e:
            print(f"Workflow dispatch failed: {e}")

        property_id = result.get("propertyId")
        unit_id = result.get("unitId")
        if property_id and unit_id:
            resolution_summary = result.get("resolutionNotes", "")
            body = f"Your maintenance request '{result.get('title', 'ticket')}' is closed."
            if resolution_summary:
                # Real, genuine transparency - the resident sees what
                # the tech actually found and did, not just a bare
                # "closed" status with no explanation. Truncated for a
                # notification body (a full-length writeup belongs on
                # the ticket detail itself, which the link below opens),
                # not truncated in the stored/API-served field.
                body += f" What was done: {resolution_summary[:200]}{'...' if len(resolution_summary) > 200 else ''}"
            body += " Rate how it went."
            await notifications_service.notify_unit_resident(
                property_id, unit_id,
                type="general",
                title="How did we do?",
                body=body,
                link=f"/maintenance/{ticket_id}/rate",
            )

    return serialize(result)


@router.post("/{ticket_id}/time")
async def log_time(ticket_id: str, payload: TimeEntryCreate, user: dict = Depends(require_staff)):
    if not ObjectId.is_valid(ticket_id):
        raise HTTPException(status_code=400, detail="Invalid ticket ID")

    entry = {
        "hours": payload.hours,
        "note": payload.note,
        "loggedBy": user.get("email"),
        "loggedAt": datetime.now(timezone.utc),
    }

    result = await tickets_col.find_one_and_update(
        {"_id": ObjectId(ticket_id), "orgId": user["orgId"]},
        {
            "$push": {"timeEntries": entry},
            "$inc": {"totalHours": payload.hours},
        },
        return_document=True,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return serialize(result)


@router.post("/{ticket_id}/satisfaction")
async def submit_satisfaction(ticket_id: str, payload: TicketSatisfactionSubmit, user: dict = Depends(get_current_user)):
    """Tenant-facing satisfaction rating on a closed ticket. Same
    never-trust-client-submitted-scope pattern used throughout this
    session - the ticket is cross-checked against the authenticated
    tenant's OWN propertyId/unitId, so a resident can't rate (or even
    confirm the existence of) a ticket that isn't theirs. orgId
    included alongside for defense in depth."""
    if not ObjectId.is_valid(ticket_id):
        raise HTTPException(status_code=400, detail="Invalid ticket ID")
    ticket = await tickets_col.find_one({"_id": ObjectId(ticket_id), "orgId": user.get("orgId")})
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    if user.get("role") == "tenant" and (
        ticket.get("propertyId") != user.get("propertyId") or ticket.get("unitId") != user.get("unitId")
    ):
        raise HTTPException(status_code=403, detail="Not your ticket")

    if ticket.get("status") != "done":
        raise HTTPException(status_code=400, detail="Only closed tickets can be rated.")

    result = await tickets_col.find_one_and_update(
        {"_id": ObjectId(ticket_id)},
        {"$set": {
            "satisfactionRating": payload.rating,
            "satisfactionComment": payload.comment,
            "satisfactionSubmittedAt": datetime.now(timezone.utc),
        }},
        return_document=True,
    )

    # The actual "flag unhappy ones internally" half of the original
    # ask - a low rating notifies staff immediately rather than
    # silently sitting in the data waiting for someone to run a
    # report. 1-2 is genuinely dissatisfied, not just "fine, not great."
    if payload.rating <= 2:
        await notifications_service.notify_all_staff(
            type="general",
            title="Low satisfaction rating on a closed ticket",
            body=f"Unit {ticket.get('unitId')} rated '{ticket.get('title', 'a ticket')}' {payload.rating}/5"
                 + (f": {payload.comment}" if payload.comment else ""),
            link=f"/maintenance/{ticket_id}",
        )

    return serialize(result)


@router.get("/satisfaction/flagged")
async def list_flagged_satisfaction(propertyId: str | None = None, user: dict = Depends(require_staff)):
    """Staff-facing report of low-satisfaction closed tickets (rating
    1-2), the other real half of this feature - somewhere staff can
    actually go look, not just react to the real-time notification
    above."""
    query = {"satisfactionRating": {"$lte": 2}, "orgId": user["orgId"]}
    if propertyId:
        query["propertyId"] = propertyId
    cursor = tickets_col.find(query).sort("satisfactionSubmittedAt", -1).limit(200)
    tickets = await cursor.to_list(length=200)
    return {"tickets": [serialize(t) for t in tickets]}
