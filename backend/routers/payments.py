"""
Payments / collections endpoints.

POST  /api/payments                 -> create a charge (e.g. this month's rent)
GET   /api/payments?status=&propertyId=&unitId= -> list charges
PATCH /api/payments/:id/record      -> record a payment against a charge
GET   /api/payments/delinquent      -> charges that are past due and not fully paid
POST  /api/payments/:id/checkout    -> real Stripe ACH Direct Debit checkout
POST  /api/payments/setup-intent    -> starts bank-account linking for a resident
POST  /api/payments/autopay/enroll  -> saves a linked bank account as the resident's
                                        autopay payment method
POST  /api/payments/stripe-webhook  -> Stripe calls this when an ACH payment's real,
                                        eventual outcome is known (succeeded/failed) -
                                        see stripe_service.py's module docstring for
                                        why ACH specifically needs this rather than
                                        trusting the initial API response

This is a ledger, not a payments processor by itself — it tracks what's
owed and what's been recorded as received, and now genuinely can move
money through Stripe ACH Direct Debit once STRIPE_SECRET_KEY and
STRIPE_WEBHOOK_SECRET are configured (see stripe_service.py). Until
then, /checkout and /setup-intent fail with an honest 503, not a
silent no-op.
"""
from datetime import datetime, timezone
import os

from fastapi import APIRouter, HTTPException, Depends, Request
from bson import ObjectId

from db import payments_col, users_col, late_notices_col
from date_utils import parse_date_utc
from models import ChargeCreate, PaymentRecord, CheckoutSessionCreate, PaymentReturn, AutopayEnroll
from auth import require_staff, get_current_user
from services.events import emit_event
from stripe_service import (
    StripeNotConfigured,
    StripePayError,
    get_or_create_customer_async,
    create_setup_intent_async,
    create_ach_payment_intent_async,
    construct_webhook_event,
)
from audit_service import log_action
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
    paidMonth: str | None = None,
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

    if paidMonth:
        # Real month-range filter, matching the exact 'YYYY-MM' format
        # dashboard.py's revenue-trend already groups by - this is what
        # makes clicking a specific month's bar on that chart genuinely
        # useful, landing on exactly the real charges that made up that
        # bar, not an unfiltered list the person has to re-filter by hand.
        try:
            year, month = paidMonth.split("-")
            year, month = int(year), int(month)
        except (ValueError, AttributeError):
            raise HTTPException(status_code=400, detail="paidMonth must be in 'YYYY-MM' format.")
        month_start = datetime(year, month, 1, tzinfo=timezone.utc)
        month_end = datetime(year + (1 if month == 12 else 0), 1 if month == 12 else month + 1, 1, tzinfo=timezone.utc)
        query["paidDate"] = {"$gte": month_start, "$lt": month_end}

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

    await log_action(
        actor_id=str(user["id"]), actor_email=user.get("email", ""),
        action="payment_recorded", target_type="payment", target_id=charge_id,
        details={"amountPaid": payload.amountPaid, "method": payload.method},
    )

    await notifications_service.notify_unit_resident(
        charge.get("propertyId"), charge.get("unitId"),
        type="payment_received",
        title="Payment received",
        body=f"${payload.amountPaid:.2f} recorded for {charge.get('description', 'your charge')}",
        link="/payments",
    )

    try:
        await emit_event("payment_received", {
            "chargeId": charge_id,
            "propertyId": charge.get("propertyId"),
            "unitId": charge.get("unitId"),
            "amountPaid": payload.amountPaid,
            "totalPaid": new_amount_paid,
            "amountDue": charge.get("amountDue"),
        })
    except Exception as e:
        print(f"Workflow dispatch failed: {e}")

    return serialize(result)


@router.patch("/{charge_id}/return")
async def return_payment(charge_id: str, payload: PaymentReturn, user: dict = Depends(require_staff)):
    if not ObjectId.is_valid(charge_id):
        raise HTTPException(status_code=400, detail="Invalid charge ID")

    charge = await payments_col.find_one({"_id": ObjectId(charge_id)})
    if not charge:
        raise HTTPException(status_code=404, detail="Charge not found")

    new_amount_paid = max(0, charge.get("amountPaid", 0) - payload.amount)

    updates = {
        "amountPaid": new_amount_paid,
        "returnedAt": datetime.now(timezone.utc),
        "returnReason": payload.reason,
        "updatedAt": datetime.now(timezone.utc),
    }

    result = await payments_col.find_one_and_update(
        {"_id": ObjectId(charge_id)}, {"$set": updates}, return_document=True
    )

    await notifications_service.notify_unit_resident(
        charge.get("propertyId"), charge.get("unitId"),
        type="payment_returned",
        title="Payment returned",
        body=f"${payload.amount:.2f} was returned for {charge.get('description', 'your charge')}",
        link="/payments",
    )

    try:
        await emit_event("payment_returned", {
            "chargeId": charge_id,
            "propertyId": charge.get("propertyId"),
            "unitId": charge.get("unitId"),
            "amountReturned": payload.amount,
            "reason": payload.reason,
        })
    except Exception as e:
        print(f"Workflow dispatch failed: {e}")

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

    payment_method_id = user.get("autopayPaymentMethodId")
    if not payment_method_id:
        raise HTTPException(
            status_code=400,
            detail="No bank account linked. Set one up under Autopay first.",
        )

    remaining_due = charge.get("amountDue", 0) - charge.get("amountPaid", 0)
    if remaining_due <= 0:
        raise HTTPException(status_code=400, detail="This charge is already fully paid.")

    try:
        customer_id = await get_or_create_customer_async(
            str(user["id"]), user["email"], user.get("name", "")
        )
        result = await create_ach_payment_intent_async(
            customer_id,
            payment_method_id,
            amount_cents=round(remaining_due * 100),
            description=charge.get("description", "Rent payment"),
        )
    except StripeNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except StripePayError as exc:
        raise HTTPException(status_code=402, detail=str(exc))

    # Record the attempt as "processing", not "paid" - ACH takes 4-5
    # business days to actually clear. The ledger only moves to paid
    # once the Stripe webhook confirms payment_intent.succeeded (see
    # stripe_webhook below). Storing the PaymentIntent id here is what
    # lets that webhook find its way back to this exact charge later.
    await payments_col.update_one(
        {"_id": ObjectId(charge_id)},
        {"$set": {"stripePaymentIntentId": result["paymentIntentId"], "paymentProcessingStatus": result["status"]}},
    )
    return {"status": result["status"], "paymentIntentId": result["paymentIntentId"]}


@router.get("/stripe-config")
async def get_stripe_config(user: dict = Depends(get_current_user)):
    """Returns the Stripe publishable key so the frontend can initialize
    Stripe.js, or null if it isn't configured yet. Safe to expose - a
    publishable key is, by Stripe's own design, meant to be public (it's
    literally embedded in every Stripe.js page load on any site that
    uses it); the secret key stays server-side only, in
    STRIPE_SECRET_KEY, never returned by this or any endpoint. This
    lets the frontend show an honest "autopay isn't set up yet" state
    instead of attempting to load Stripe.js against a key that doesn't
    exist, or worse, a hardcoded placeholder key baked into the
    frontend bundle that silently breaks on every deploy until someone
    remembers to update it."""
    key = os.getenv("STRIPE_PUBLISHABLE_KEY")
    return {"publishableKey": key}


@router.post("/setup-intent")
async def create_bank_setup_intent(user: dict = Depends(get_current_user)):
    """Starts linking a bank account for the current user. Returns a
    Stripe client_secret the frontend hands to Stripe.js to complete
    verification entirely in the browser - this endpoint's only job is
    getting (or creating) the Stripe Customer this SetupIntent attaches
    to."""
    try:
        customer_id = await get_or_create_customer_async(
            str(user["id"]), user["email"], user.get("name", "")
        )
        result = await create_setup_intent_async(customer_id)
    except StripeNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except StripePayError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    await users_col.update_one({"_id": user["id"]}, {"$set": {"stripeCustomerId": customer_id}})
    return result


@router.post("/autopay/enroll")
async def enroll_autopay(payload: AutopayEnroll, user: dict = Depends(get_current_user)):
    """Saves a successfully-linked bank account (paymentMethodId, from
    the completed SetupIntent above) as this resident's autopay method.
    Doesn't itself charge anything or schedule a recurring job - that's
    real follow-on work (a scheduled check, same external-cron pattern
    as late fees and preventive maintenance) once this enrollment step
    is confirmed working end-to-end."""
    await users_col.update_one(
        {"_id": user["id"]},
        {"$set": {"autopayPaymentMethodId": payload.paymentMethodId, "autopayEnabled": True}},
    )
    return {"autopayEnabled": True}


@router.post("/autopay/cancel")
async def cancel_autopay(user: dict = Depends(get_current_user)):
    await users_col.update_one(
        {"_id": user["id"]},
        {"$set": {"autopayEnabled": False}},
    )
    return {"autopayEnabled": False}


@router.post("/stripe-webhook")
async def stripe_webhook(request: Request):
    """Real, security-boundary-verified endpoint - Stripe signs every
    webhook request, and construct_webhook_event rejects anything that
    isn't genuinely from Stripe before any of its contents are trusted.
    Public (no user auth possible here, same as Twilio's voice webhook
    in routers/telephony.py), so this signature check is the only thing
    standing between this endpoint and someone POSTing a fake "payment
    succeeded" event at it."""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    try:
        event = construct_webhook_event(payload, sig_header)
    except (StripeNotConfigured, StripePayError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    intent = event["data"]["object"]
    intent_id = intent.get("id")

    if event["type"] == "payment_intent.succeeded":
        charge = await payments_col.find_one({"stripePaymentIntentId": intent_id})
        if charge:
            amount_paid = intent.get("amount_received", 0) / 100
            await payments_col.update_one(
                {"_id": charge["_id"]},
                {"$set": {
                    "amountPaid": charge.get("amountPaid", 0) + amount_paid,
                    "paidDate": datetime.now(timezone.utc),
                    "paymentProcessingStatus": "succeeded",
                }},
            )
    elif event["type"] == "payment_intent.payment_failed":
        charge = await payments_col.find_one({"stripePaymentIntentId": intent_id})
        if charge:
            # Do NOT touch amountPaid here - a failed PaymentIntent
            # never actually moved money, so there's nothing to reverse
            # on the ledger, just a status to record so staff can see
            # this charge's autopay attempt didn't go through and needs
            # follow-up.
            await payments_col.update_one(
                {"_id": charge["_id"]},
                {"$set": {"paymentProcessingStatus": "failed"}},
            )

    return {"received": True}


@router.get("/late-notices")
async def list_late_notices(propertyId: str | None = None, unitId: str | None = None, user: dict = Depends(get_current_user)):
    """Real notices generated by admin.py's late-fee automation - see
    that file for why these are deliberately factual, not
    legal-conclusion documents. A tenant only ever sees their own
    unit's notices, scoped from their own server-verified record, same
    pattern used throughout this session; staff can filter by any
    property/unit."""
    query = {}
    if user.get("role") == "tenant":
        query["propertyId"] = user.get("propertyId")
        query["unitId"] = user.get("unitId")
    else:
        if propertyId:
            query["propertyId"] = propertyId
        if unitId:
            query["unitId"] = unitId

    cursor = late_notices_col.find(query).sort("createdAt", -1).limit(200)
    notices = await cursor.to_list(length=200)
    for n in notices:
        n["id"] = str(n.pop("_id"))
        if isinstance(n.get("createdAt"), datetime):
            n["createdAt"] = n["createdAt"].isoformat()
    return {"notices": notices}
