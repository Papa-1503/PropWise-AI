"""
Maintenance ticket endpoints.

GET   /api/maintenance/tickets            -> list, filterable by propertyId/status
POST  /api/maintenance/tickets            -> create a ticket (used directly by staff,
                                              and auto-called from the inspection flow)
PATCH /api/maintenance/tickets/:id        -> update status/assignee/priority
"""
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends
from bson import ObjectId

from db import tickets_col
from models import TicketCreate, TicketUpdate
import notifications_service
from auth import require_staff, get_current_user
from services.events import emit_event

router = APIRouter(prefix="/api/maintenance/tickets", tags=["maintenance"])


def serialize(ticket: dict) -> dict:
    ticket["id"] = str(ticket.pop("_id"))
    return ticket


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
    result = await tickets_col.insert_one(doc)
    doc["_id"] = result.inserted_id
    if doc.get("priority") == "urgent":
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
