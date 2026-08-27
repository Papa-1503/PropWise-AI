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
"""
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends
from bson import ObjectId

from db import tickets_col, users_col
from models import TicketCreate, TicketUpdate, TimeEntryCreate
import notifications_service
from auth import require_staff, get_current_user
from services.events import emit_event
from services.ticket_dedup import find_existing_open_duplicate, record_duplicate_occurrence

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
    query = {}
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
    doc["status"] = "open"
    doc["createdAt"] = datetime.now(timezone.utc)
    if user["role"] == "tenant":
        doc["propertyId"] = user.get("propertyId")
        doc["unitId"] = user.get("unitId")
        doc["source"] = "resident"

    existing_duplicate = await find_existing_open_duplicate(
        doc.get("propertyId"), doc.get("unitId"), doc.get("title")
    )
    if existing_duplicate:
        await record_duplicate_occurrence(existing_duplicate)
        existing_duplicate["_id"] = str(existing_duplicate["_id"])
        return {**existing_duplicate, "wasExistingDuplicate": True}

    assigned_tech = None
    if doc.get("source") == "resident" and doc.get("propertyId"):
        assigned_tech = await find_tech_for_property(doc["propertyId"])
        if assigned_tech:
            doc["assignee"] = assigned_tech.get("email")

    result = await tickets_col.insert_one(doc)
    doc["_id"] = result.inserted_id

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
    updates["updatedAt"] = datetime.now(timezone.utc)
    result = await tickets_col.find_one_and_update(
        {"_id": ObjectId(ticket_id)},
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
        {"_id": ObjectId(ticket_id)},
        {
            "$push": {"timeEntries": entry},
            "$inc": {"totalHours": payload.hours},
        },
        return_document=True,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return serialize(result)
