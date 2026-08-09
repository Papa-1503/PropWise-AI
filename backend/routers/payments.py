"""
Payments / collections endpoints.

POST  /api/payments                 -> create a charge (e.g. this month's rent)
GET   /api/payments?status=&propertyId=&unitId= -> list charges
PATCH /api/payments/:id/record      -> record a payment against a charge
GET   /api/payments/delinquent      -> charges that are past due and not fully paid
POST  /api/payments/:id/checkout    -> placeholder for a real payment processor

This is a ledger, not a payments processor — it tracks what's owed and
what's been recorded as received. It does not move money. Wire a real
processor (Stripe, etc.) behind /record and /checkout if you want actual
transactions instead of manually-recorded payments.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends
from bson import ObjectId

from db import payments_col
from date_utils import parse_date_utc
from models import ChargeCreate, PaymentRecord, CheckoutSessionCreate
from auth import require_staff, get_current_user
import notifications_service

router = APIRouter(prefix="/api/payments", tags=["payments"])


def compute_status(charge: dict) -> str:
    if charge.get("amountPaid", 0) >= charge.get("amountDue", 0):
        return "paid"
    due = charge.get("dueDate")
    if isinstance(due, datetime):
        if due.tzinfo is None:
            due = due.replace(tzinfo=timezone.utc)
        if due < datetime.now(timezone.utc):
            return "late"
    return "pending"


def serialize(charge: dict) -> dict:
    charge["id"] = str(charge.pop("_id"))
    charge["status"] = compute_status(charge)
    for field in ("dueDate", "paidDate", "createdAt"):
        if isinstance(charge.get(field), datetime):
            charge[field] = charge[field].isoformat()
    return charge


@router.post("")
async def create_charge(payload: ChargeCreate, user: dict = Depends(require_staff)):
    doc = payload.model_dump()
    doc["dueDate"] = parse_date_utc(doc["dueDate"])
    doc["amountPaid"] = 0.0
    doc["paidDate"] = None
    doc["createdAt"] = datetime.now(timezone.utc)
    result = await payments_col.insert_one(doc)
    doc["_id"] = result.inserted_id
    return serialize(doc)


@router.get("")
async def list_charges(
    propertyId: str | None = None,
    unitId: str | None = None,
    status: str | None = None,
    user: dict = Depends(get_current_user),
):
    query = {}
    if user["role"] == "tenant":
        query["propertyId"] = user.get("propertyId")
        query["unitId"] = user.get("unitId")
    else:
        if propertyId:
            query["propertyId"] = propertyId
        if unitId:
            query["unitId"] = unitId

    cursor = payments_col.find(query).sort("dueDate", -1).limit(500)
    charges = [serialize(c) for c in await cursor.to_list(length=500)]
    if status:
        charges = [c for c in charges if c["status"] == status]
    return {"charges": charges}


@router.get("/delinquent")
async def list_delinquent(propertyId: str | None = None, user: dict = Depends(require_staff)):
    query = {"propertyId": propertyId} if propertyId else {}
    now = datetime.now(timezone.utc)
    cursor = payments_col.find({**query, "dueDate": {"$lt": now}})
    all_past_due = await cursor.to_list(length=1000)
    delinquent = [serialize(c) for c in all_past_due]
    delinquent = [c for c in delinquent if c["status"] == "late"]
    total_outstanding = sum(c["amountDue"] - c["amountPaid"] for c in delinquent)
    return {"charges": delinquent, "count": len(delinquent), "totalOutstanding": round(total_outstanding, 2)}


@router.patch("/{charge_id}/record")
async def record_payment(charge_id: str, payload: PaymentRecord, user: dict = Depends(require_staff)):
    if not ObjectId.is_valid(charge_id):
        raise HTTPException(status_code=400, detail="Invalid charge ID")

    charge = await payments_col.find_one({"_id": ObjectId(charge_id)})
    if not charge:
        raise HTTPException(status_code=404, detail="Charge not found")

    new_amount_paid = charge.get("amountPaid", 0) + payload.amountPaid
    paid_date = parse_date_utc(payload.paidDate) if payload.paidDate else datetime.now(timezone.utc)

    updates = {
        "amountPaid": new_amount_paid,
        "paidDate": paid_date,
        "recordedBy": user.get("email"),
        "updatedAt": datetime.now(timezone.utc),
    }
    if payload.method:
        updates["method"] = payload.method
    if payload.note:
        updates["paymentNote"] = payload.note

    result = await payments_col.find_one_and_update(
        {"_id": ObjectId(charge_id)}, {"$set": updates}, return_document=True
    )

    await notifications_service.notify_unit_resident(
        charge.get("propertyId"), charge.get("unitId"),
        type="payment_received",
        title="Payment received",
        body=f"${payload.amountPaid:.2f} recorded for {charge.get('description', 'your charge')}",
        link="/payments",
    )

    return serialize(result)


@router.post("/{charge_id}/checkout")
async def create_checkout_session(charge_id: str, payload: CheckoutSessionCreate, user: dict = Depends(get_current_user)):
    if not ObjectId.is_valid(charge_id):
        raise HTTPException(status_code=400, detail="Invalid charge ID")
    charge = await payments_col.find_one({"_id": ObjectId(charge_id)})
    if not charge:
        raise HTTPException(status_code=404, detail="Charge not found")

    if user["role"] == "tenant" and (
        charge.get("propertyId") != user.get("propertyId")
        or charge.get("unitId") != user.get("unitId")
    ):
        raise HTTPException(status_code=403, detail="Not your charge")

    raise HTTPException(
        status_code=501,
        detail="Online payment is not yet configured. Contact staff to pay this charge another way.",
    )
