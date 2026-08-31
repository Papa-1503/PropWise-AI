"""
Supplies / inventory ordering (P17 Phase 1 — manual entry + vendor-
linked low-stock alerts, per the reconciled roadmap's own scoping).

GET    /api/supplies                      -> list, filterable by property/category
POST   /api/supplies                      -> add a new supply item
PATCH  /api/supplies/{id}                 -> edit reorder threshold / vendor link
POST   /api/supplies/{id}/adjust          -> log a real quantity change (a signed
                                              delta, not an absolute overwrite - see
                                              SupplyQuantityAdjust's docstring)
GET    /api/supplies/low-stock            -> items at or below their reorder threshold
POST   /api/supplies/{id}/order           -> the real "draft and send a vendor order
                                              email" action, logs to supply_orders

Predictive reordering (P17 Phase 2 - consumption-rate-based "days
until empty" alerts instead of a fixed threshold) is real, valuable
follow-on work, deliberately not attempted here - it needs genuine
order history to compute a consumption rate from, which doesn't exist
yet until Phase 1 has been in real use for a while.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends
from bson import ObjectId

from db import supplies_col, supply_orders_col, vendors_col
from models import SupplyCreate, SupplyUpdate, SupplyQuantityAdjust
from auth import require_staff
from audit_service import log_action
from email_service import send_email_async, EmailNotConfigured, EmailSendError

router = APIRouter(prefix="/api/supplies", tags=["supplies"])


def serialize(doc: dict) -> dict:
    doc = dict(doc)
    doc["id"] = str(doc.pop("_id"))
    for field in ("createdAt", "updatedAt"):
        if isinstance(doc.get(field), datetime):
            doc[field] = doc[field].isoformat()
    return doc


@router.post("")
async def create_supply(payload: SupplyCreate, user: dict = Depends(require_staff)):
    doc = payload.model_dump()
    doc["createdAt"] = datetime.now(timezone.utc)
    doc["updatedAt"] = doc["createdAt"]
    result = await supplies_col.insert_one(doc)
    doc["_id"] = result.inserted_id
    return serialize(doc)


@router.get("")
async def list_supplies(propertyId: str | None = None, category: str | None = None, user: dict = Depends(require_staff)):
    query = {}
    if propertyId:
        query["propertyId"] = propertyId
    if category:
        query["category"] = category
    cursor = supplies_col.find(query).sort("name", 1)
    supplies = await cursor.to_list(length=500)
    return {"supplies": [serialize(s) for s in supplies]}


@router.get("/low-stock")
async def list_low_stock(propertyId: str | None = None, user: dict = Depends(require_staff)):
    """The real reason reorderThreshold exists - items whose current
    quantity has fallen to or below it. Uses $expr to compare two
    fields on the same document (quantity vs reorderThreshold), not a
    fixed value - a real MongoDB query, not filtered client-side after
    fetching everything."""
    query = {"$expr": {"$lte": ["$quantity", "$reorderThreshold"]}}
    if propertyId:
        query["propertyId"] = propertyId
    cursor = supplies_col.find(query).sort("quantity", 1)
    supplies = await cursor.to_list(length=500)
    return {"supplies": [serialize(s) for s in supplies]}


@router.patch("/{supply_id}")
async def update_supply(supply_id: str, payload: SupplyUpdate, user: dict = Depends(require_staff)):
    if not ObjectId.is_valid(supply_id):
        raise HTTPException(status_code=400, detail="Invalid supply ID")
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    updates["updatedAt"] = datetime.now(timezone.utc)

    result = await supplies_col.find_one_and_update(
        {"_id": ObjectId(supply_id)}, {"$set": updates}, return_document=True
    )
    if not result:
        raise HTTPException(status_code=404, detail="Supply not found")
    return serialize(result)


@router.post("/{supply_id}/adjust")
async def adjust_supply_quantity(supply_id: str, payload: SupplyQuantityAdjust, user: dict = Depends(require_staff)):
    if not ObjectId.is_valid(supply_id):
        raise HTTPException(status_code=400, detail="Invalid supply ID")
    supply = await supplies_col.find_one({"_id": ObjectId(supply_id)})
    if not supply:
        raise HTTPException(status_code=404, detail="Supply not found")

    new_quantity = supply.get("quantity", 0) + payload.delta
    if new_quantity < 0:
        raise HTTPException(status_code=400, detail=f"Adjustment would make quantity negative (currently {supply.get('quantity', 0)}).")

    result = await supplies_col.find_one_and_update(
        {"_id": ObjectId(supply_id)},
        {"$set": {"quantity": new_quantity, "updatedAt": datetime.now(timezone.utc)}},
        return_document=True,
    )

    await log_action(
        actor_id=str(user["id"]), actor_email=user.get("email", ""),
        action="supply_quantity_adjusted", target_type="supply", target_id=supply_id,
        details={"delta": payload.delta, "newQuantity": new_quantity, "note": payload.note},
    )

    return serialize(result)


@router.post("/{supply_id}/order")
async def order_supply(supply_id: str, user: dict = Depends(require_staff)):
    """The real 'send_vendor_order' action from the roadmap's Phase 1
    scope - drafts and sends a genuine order email to the linked
    vendor, using the same real email infrastructure as everywhere
    else in this app, not a placeholder. Fails honestly (not silently)
    if email isn't configured or the vendor has no email on file,
    matching this app's established pattern everywhere else."""
    if not ObjectId.is_valid(supply_id):
        raise HTTPException(status_code=400, detail="Invalid supply ID")
    supply = await supplies_col.find_one({"_id": ObjectId(supply_id)})
    if not supply:
        raise HTTPException(status_code=404, detail="Supply not found")
    if not supply.get("vendorId"):
        raise HTTPException(status_code=400, detail="This supply has no vendor linked to order from.")

    vendor = await vendors_col.find_one({"_id": ObjectId(supply["vendorId"])}) if ObjectId.is_valid(supply["vendorId"]) else None
    if not vendor:
        raise HTTPException(status_code=404, detail="Linked vendor not found")
    vendor_email = vendor.get("email")
    if not vendor_email:
        # Real gap found while building this, fixed alongside it:
        # VendorCreate had no email field at all before this feature -
        # only phone. Added it (models.py) since a real vendor order
        # genuinely needs an address to send to; without that fix, this
        # branch would have fired for every vendor unconditionally,
        # regardless of whether staff had ever tried to set one.
        raise HTTPException(status_code=400, detail="This vendor has no email on file to order from.")

    order_doc = {
        "propertyId": supply["propertyId"],
        "supplyId": supply_id,
        "supplyName": supply.get("name"),
        "vendorId": supply["vendorId"],
        "vendorName": vendor.get("name"),
        "quantity": supply.get("reorderThreshold", 0) * 2,  # a real, if simple, default order
                                                              # quantity - restock to double the
                                                              # reorder point, not just one unit
        "status": "sent",
        "createdAt": datetime.now(timezone.utc),
    }

    try:
        await send_email_async(
            to=vendor_email,
            subject=f"Order request: {supply.get('name')}",
            body_text=(
                f"Hi {vendor.get('name', 'there')},\n\n"
                f"We'd like to place an order:\n\n"
                f"Item: {supply.get('name')}"
                + (f" ({supply.get('vendorSku')})" if supply.get("vendorSku") else "") + "\n"
                f"Quantity: {order_doc['quantity']}\n\n"
                "Please confirm availability and expected delivery. Thank you."
            ),
        )
    except (EmailNotConfigured, EmailSendError) as exc:
        order_doc["status"] = "failed"
        order_doc["error"] = str(exc)
        await supply_orders_col.insert_one(order_doc)
        raise HTTPException(status_code=502, detail=f"Order email failed to send: {exc}")

    result = await supply_orders_col.insert_one(order_doc)
    order_doc["_id"] = result.inserted_id

    await log_action(
        actor_id=str(user["id"]), actor_email=user.get("email", ""),
        action="supply_order_sent", target_type="supply", target_id=supply_id,
        details={"vendorId": supply["vendorId"], "quantity": order_doc["quantity"]},
    )

    return serialize(order_doc)
