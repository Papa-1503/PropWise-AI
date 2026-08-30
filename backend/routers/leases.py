"""
Lease endpoints.

GET   /api/leases?propertyId=&expiringWithinDays=   -> list, optionally filtered
POST  /api/leases                                   -> create a lease
PATCH /api/leases/:id                                -> update renewal status / balance
"""
from datetime import datetime, timedelta, timezone
import secrets
import string
import os
import uuid

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from bson import ObjectId
import cloudinary
import cloudinary.uploader

from db import leases_col, documents_col, properties_col
from models import LeaseCreate, LeaseUpdate, InsurancePolicyUpdate
from date_utils import parse_date_utc
from auth import require_staff, require_staff_or_owner, get_current_user
from services.events import emit_event
from audit_service import log_action

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True,
)
router = APIRouter(prefix="/api/leases", tags=["leases"])

# Excludes visually ambiguous characters (0/O, 1/I/l) so a resident can
# type the code correctly from a printed/texted invite without confusion.
_INVITE_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def generate_invite_code() -> str:
    return "".join(secrets.choice(_INVITE_CODE_ALPHABET) for _ in range(8))



def serialize(lease: dict) -> dict:
    lease["id"] = str(lease.pop("_id"))
    for field in ("startDate", "endDate"):
        if isinstance(lease.get(field), datetime):
            lease[field] = lease[field].isoformat()
    return lease


@router.get("")
async def list_leases(propertyId: str | None = None, expiringWithinDays: int | None = None, user: dict = Depends(require_staff_or_owner)):
    query: dict = {}
    if propertyId:
        query["propertyId"] = propertyId
    if expiringWithinDays is not None:
        cutoff = datetime.now(timezone.utc) + timedelta(days=expiringWithinDays)
        query["endDate"] = {"$lte": cutoff}

    # Real scoping, not just a role gate: without this, an owner could
    # either omit propertyId and see every lease in the whole system,
    # or pass a propertyId they don't actually own and see that other
    # owner's residents. When propertyId IS given, verify it's actually
    # theirs; when it's omitted, restrict to their own properties
    # automatically instead — a genuinely useful "all my leases across
    # everything I own" view, matching how owner_dashboard already
    # aggregates across an owner's full portfolio, rather than just
    # rejecting the request for not specifying one.
    if user["role"] == "owner":
        owned_ids = {
            str(p["_id"]) for p in await properties_col.find({"ownerId": user["id"]}, {"_id": 1}).to_list(length=500)
        }
        if propertyId:
            if propertyId not in owned_ids:
                raise HTTPException(status_code=403, detail="You don't have access to this property.")
        else:
            query["propertyId"] = {"$in": list(owned_ids)}

    cursor = leases_col.find(query).sort("endDate", 1)
    leases = await cursor.to_list(length=500)
    return {"leases": [serialize(l) for l in leases]}


@router.get("/mine")
async def my_lease(user: dict = Depends(get_current_user)):
    """A tenant fetching their OWN lease — genuinely didn't exist before.
    list_leases above allows staff and owners, but never tenants directly,
    so there was no way for a tenant to see their own lease details
    through the API at all.
    Matched on propertyId+unitId (set during invite-code registration),
    not residentEmail, since that's the more robust match — a tenant's
    login email isn't guaranteed to exactly match what staff typed into
    the lease's residentEmail field when the lease was created."""
    if user["role"] != "tenant":
        raise HTTPException(status_code=403, detail="Only tenants can use this endpoint.")
    lease = await leases_col.find_one({"propertyId": user.get("propertyId"), "unitId": user.get("unitId")})
    if not lease:
        return {"lease": None}
    return {"lease": serialize(lease)}


@router.post("")
async def create_lease(payload: LeaseCreate, user: dict = Depends(require_staff)):
    doc = payload.model_dump()
    doc["startDate"] = parse_date_utc(doc["startDate"])
    doc["endDate"] = parse_date_utc(doc["endDate"])
    doc["balance"] = 0
    doc["inviteCode"] = generate_invite_code()
    doc["createdAt"] = datetime.now(timezone.utc)
    result = await leases_col.insert_one(doc)
    doc["_id"] = result.inserted_id

    await log_action(
        actor_id=str(user["_id"]), actor_email=user.get("email", ""),
        action="lease_created", target_type="lease", target_id=str(result.inserted_id),
        details={"propertyId": doc.get("propertyId"), "unitId": doc.get("unitId"), "residentName": doc.get("residentName")},
    )

    try:
        await emit_event("lease_created", {
            "leaseId": str(result.inserted_id),
            "propertyId": doc.get("propertyId"),
            "unitId": doc.get("unitId"),
            "residentEmail": doc.get("residentEmail"),
            "residentName": doc.get("residentName"),
        })
    except Exception as e:
        print(f"Workflow dispatch failed: {e}")

    return serialize(doc)


@router.patch("/{lease_id}")
async def update_lease(lease_id: str, payload: LeaseUpdate, user: dict = Depends(require_staff)):
    if not ObjectId.is_valid(lease_id):
        raise HTTPException(status_code=400, detail="Invalid lease ID")
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    if "endDate" in updates:
        updates["endDate"] = parse_date_utc(updates["endDate"])
    result = await leases_col.find_one_and_update(
        {"_id": ObjectId(lease_id)}, {"$set": updates}, return_document=True
    )
    if not result:
        raise HTTPException(status_code=404, detail="Lease not found")

    await log_action(
        actor_id=str(user["_id"]), actor_email=user.get("email", ""),
        action="lease_updated", target_type="lease", target_id=lease_id,
        details={"fields": list(updates.keys())},
    )

    return serialize(result)

@router.post("/{lease_id}/generate-document")
async def generate_lease_document(lease_id: str, user: dict = Depends(require_staff)):
    if not ObjectId.is_valid(lease_id):
        raise HTTPException(status_code=400, detail="Invalid lease ID")
    lease = await leases_col.find_one({"_id": ObjectId(lease_id)})
    if not lease:
        raise HTTPException(status_code=404, detail="Lease not found")

    # Idempotency: if an unsigned document already exists for this lease,
    # return it instead of creating another one. Without this, clicking
    # "Generate document" more than once (easy to do — no visible sign
    # a document already exists) silently creates duplicate pending
    # documents, which would confuse a tenant seeing multiple "please
    # sign" requests for the same lease.
    existing = await documents_col.find_one({"leaseId": lease_id, "status": "pending"})
    if existing:
        return {"documentId": str(existing["_id"]), "alreadyExisted": True}

    if not lease.get("residentEmail"):
        raise HTTPException(status_code=400, detail="Lease has no resident email on file")

    start = lease.get("startDate")
    end = lease.get("endDate")
    start_str = start.strftime("%B %d, %Y") if isinstance(start, datetime) else str(start)
    end_str = end.strftime("%B %d, %Y") if isinstance(end, datetime) else str(end)

    content = (
        f"This lease agreement is between the property and {lease.get('residentName', 'the resident')} "
        f"for unit {lease.get('unitId')}.\n\n"
        f"Lease term: {start_str} through {end_str}.\n\n"
        f"Monthly rent: ${lease.get('rent', 0):,.2f}.\n\n"
        f"By signing below, the resident acknowledges agreement to the terms above. "
        f"This document was generated from lease record {lease_id}."
    )

    doc = {
        "tenantEmail": lease["residentEmail"],
        "leaseId": lease_id,
        "title": f"Lease Agreement - Unit {lease.get('unitId')}",
        "content": content,
        "status": "pending",
        "signedByName": None,
        "signedAt": None,
        "createdAt": datetime.now(timezone.utc),
    }
    result = await documents_col.insert_one(doc)
    return {"documentId": str(result.inserted_id), "alreadyExisted": False}


@router.patch("/{lease_id}/insurance-policy")
async def update_insurance_policy(lease_id: str, payload: InsurancePolicyUpdate, user: dict = Depends(require_staff)):
    """Real renters insurance requirement tracking. Policy details are
    entered separately from the actual proof-of-insurance document
    (see POST /{lease_id}/insurance-proof below) - a resident might
    call in their carrier and policy number before the certificate
    itself is ever uploaded, or the reverse."""
    if not ObjectId.is_valid(lease_id):
        raise HTTPException(status_code=400, detail="Invalid lease ID")
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    if "expirationDate" in updates:
        updates["expirationDate"] = parse_date_utc(updates["expirationDate"])
    updates = {f"insurance{k[0].upper()}{k[1:]}": v for k, v in updates.items()}

    result = await leases_col.find_one_and_update(
        {"_id": ObjectId(lease_id)}, {"$set": updates}, return_document=True
    )
    if not result:
        raise HTTPException(status_code=404, detail="Lease not found")

    await log_action(
        actor_id=str(user["_id"]), actor_email=user.get("email", ""),
        action="insurance_policy_updated", target_type="lease", target_id=lease_id,
        details={k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in updates.items()},
    )

    return serialize(result)


@router.post("/{lease_id}/insurance-proof")
async def upload_insurance_proof(
    lease_id: str,
    file: UploadFile = File(...),
    user: dict = Depends(require_staff),
):
    """Uploads the actual certificate of insurance document. Reuses the
    same Cloudinary pattern already established in gallery.py/
    inspections.py, extended to resource_type='auto' rather than
    'image' - a real certificate of insurance is very commonly a PDF,
    not a photo, and this is the app's first upload endpoint that
    needs to accept both."""
    if not ObjectId.is_valid(lease_id):
        raise HTTPException(status_code=400, detail="Invalid lease ID")
    lease = await leases_col.find_one({"_id": ObjectId(lease_id)})
    if not lease:
        raise HTTPException(status_code=404, detail="Lease not found")

    file.file.seek(0)
    result = cloudinary.uploader.upload(
        file.file,
        folder=f"rentflow/insurance/{lease_id}",
        public_id=uuid.uuid4().hex,
        resource_type="auto",
    )

    await leases_col.update_one(
        {"_id": ObjectId(lease_id)},
        {"$set": {"insuranceProofUrl": result["secure_url"], "insuranceProofUploadedAt": datetime.now(timezone.utc)}},
    )

    await log_action(
        actor_id=str(user["_id"]), actor_email=user.get("email", ""),
        action="insurance_proof_uploaded", target_type="lease", target_id=lease_id,
    )

    return {"url": result["secure_url"]}


@router.get("/insurance-compliance")
async def insurance_compliance_report(propertyId: str | None = None, user: dict = Depends(require_staff)):
    """The actual enforcement side of this feature - who's out of
    compliance right now, for staff to act on. A lease is
    out-of-compliance if insuranceRequired is true and either no
    expiration date is on file at all, or that date has already
    passed - the exact same real-world condition a habitability or
    lease-compliance check needs to catch."""
    query = {"insuranceRequired": True}
    if propertyId:
        query["propertyId"] = propertyId
    leases = await leases_col.find(query).to_list(length=1000)

    now = datetime.now(timezone.utc)
    out_of_compliance = []
    for lease in leases:
        expiration = lease.get("insuranceExpirationDate")
        if isinstance(expiration, datetime) and expiration.tzinfo is None:
            expiration = expiration.replace(tzinfo=timezone.utc)
        if not expiration or expiration < now:
            out_of_compliance.append({
                "leaseId": str(lease["_id"]),
                "propertyId": lease.get("propertyId"),
                "unitId": lease.get("unitId"),
                "residentName": lease.get("residentName"),
                "reason": "no_policy_on_file" if not expiration else "expired",
                "expirationDate": expiration.isoformat() if expiration else None,
            })

    return {
        "requiredCount": len(leases),
        "outOfComplianceCount": len(out_of_compliance),
        "outOfCompliance": out_of_compliance,
    }
 
