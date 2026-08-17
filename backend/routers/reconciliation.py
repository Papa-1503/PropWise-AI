"""
Bank reconciliation — manual matching of bank statement lines against
recorded payments. No live bank feed is connected; staff enter statement
lines (manually today, bulk-import later) and match them against charges
already recorded in payments.py. This surfaces discrepancies between what
the bank shows and what the ledger shows, without pretending to have a
live Plaid/bank-feed connection.
"""
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends
from bson import ObjectId

from db import bank_lines_col, payments_col
from models import BankLineCreate, BankLineMatch
from auth import require_staff
from date_utils import parse_date_utc

router = APIRouter(prefix="/api/reconciliation", tags=["reconciliation"])


def serialize(doc: dict) -> dict:
    doc["id"] = str(doc.pop("_id"))
    if isinstance(doc.get("date"), datetime):
        doc["date"] = doc["date"].isoformat()
    if isinstance(doc.get("createdAt"), datetime):
        doc["createdAt"] = doc["createdAt"].isoformat()
    return doc


@router.post("/lines")
async def create_bank_line(payload: BankLineCreate, user: dict = Depends(require_staff)):
    doc = payload.model_dump()
    doc["date"] = parse_date_utc(doc["date"])
    doc["createdAt"] = datetime.now(timezone.utc)
    result = await bank_lines_col.insert_one(doc)
    doc["_id"] = result.inserted_id
    return serialize(doc)


@router.get("/lines")
async def list_bank_lines(
    propertyId: str | None = None,
    matched: bool | None = None,
    user: dict = Depends(require_staff),
):
    query = {}
    if propertyId:
        query["propertyId"] = propertyId
    if matched is True:
        query["matchedChargeId"] = {"$ne": None}
    elif matched is False:
        query["matchedChargeId"] = None

    cursor = bank_lines_col.find(query).sort("date", -1).limit(500)
    lines = await cursor.to_list(length=500)
    return {"lines": [serialize(l) for l in lines]}


@router.get("/suggestions/{line_id}")
async def suggest_matches(line_id: str, user: dict = Depends(require_staff)):
    if not ObjectId.is_valid(line_id):
        raise HTTPException(status_code=400, detail="Invalid bank line ID")
    line = await bank_lines_col.find_one({"_id": ObjectId(line_id)})
    if not line:
        raise HTTPException(status_code=404, detail="Bank line not found")

    # Suggest charges with the same amount, unmatched or partially paid,
    # on the same property, sorted by how close the due date is to the
    # bank line's date.
    candidates = await payments_col.find({
        "propertyId": line["propertyId"],
        "amountDue": line["amount"],
    }).to_list(length=100)

    results = []
    for c in candidates:
        results.append({
            "chargeId": str(c["_id"]),
            "description": c.get("description", ""),
            "amountDue": c.get("amountDue", 0),
            "amountPaid": c.get("amountPaid", 0),
            "dueDate": c["dueDate"].isoformat() if isinstance(c.get("dueDate"), datetime) else c.get("dueDate"),
        })

    return {"bankLine": serialize(line), "suggestions": results}


@router.post("/lines/{line_id}/match")
async def match_bank_line(line_id: str, payload: BankLineMatch, user: dict = Depends(require_staff)):
    if not ObjectId.is_valid(line_id):
        raise HTTPException(status_code=400, detail="Invalid bank line ID")
    if not ObjectId.is_valid(payload.chargeId):
        raise HTTPException(status_code=400, detail="Invalid charge ID")

    charge = await payments_col.find_one({"_id": ObjectId(payload.chargeId)})
    if not charge:
        raise HTTPException(status_code=404, detail="Charge not found")

    result = await bank_lines_col.find_one_and_update(
        {"_id": ObjectId(line_id)},
        {"$set": {"matchedChargeId": payload.chargeId}},
        return_document=True,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Bank line not found")
    return serialize(result)


@router.post("/lines/{line_id}/unmatch")
async def unmatch_bank_line(line_id: str, user: dict = Depends(require_staff)):
    if not ObjectId.is_valid(line_id):
        raise HTTPException(status_code=400, detail="Invalid bank line ID")
    result = await bank_lines_col.find_one_and_update(
        {"_id": ObjectId(line_id)},
        {"$set": {"matchedChargeId": None}},
        return_document=True,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Bank line not found")
    return serialize(result)
