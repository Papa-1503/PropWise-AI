"""
Organization settings — currently just the real, optional dedicated
SMS number an organization can configure (see sms_service.py's own
docstring for why this exists: without it, every organization shares
one Twilio number for SMS, which is fine for a single-tenant
deployment but a real limitation once a second organization is a real,
paying customer on the same deployment).

GET   /api/organizations/me    -> the caller's own org's real settings
PATCH /api/organizations/me    -> (org owner only) update settings

Gated to the org owner specifically, not every staff member - same
real boundary already established in routers/billing.py, since
misconfiguring the org's SMS number is a real, org-wide operational
change, not a routine staff action.
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, field_validator
from bson import ObjectId

from db import organizations_col
from auth import get_current_user

router = APIRouter(prefix="/api/organizations", tags=["organizations"])


class OrgSettingsUpdate(BaseModel):
    smsNumber: str | None = None

    @field_validator("smsNumber")
    @classmethod
    def validate_e164(cls, v):
        if v is None or v == "":
            return None
        if not v.startswith("+") or not v[1:].isdigit() or len(v) < 8:
            raise ValueError("smsNumber must be in E.164 format, e.g. +15551234567")
        return v


async def _require_org_owner(user: dict = Depends(get_current_user)) -> dict:
    """Same real ownership boundary as routers/billing.py's own
    _require_org_owner - who can change org-wide operational settings
    is narrower than who can manage day-to-day leases or tickets.
    Deliberately uses get_current_user directly, not require_staff, so
    this stays reachable even if the org's trial has expired (matching
    billing.py's own reasoning)."""
    if user.get("role") != "staff" or not user.get("isOrgOwner"):
        raise HTTPException(status_code=403, detail="Only the organization owner can manage these settings.")
    return user


def _serialize(org: dict) -> dict:
    return {
        "id": str(org["_id"]),
        "name": org.get("name"),
        "smsNumber": org.get("smsNumber"),
    }


@router.get("/me")
async def get_my_organization(user: dict = Depends(get_current_user)):
    org_id = user.get("orgId")
    if not org_id:
        raise HTTPException(status_code=400, detail="Your account isn't linked to an organization.")
    query_id = ObjectId(org_id) if ObjectId.is_valid(org_id) else org_id
    org = await organizations_col.find_one({"_id": query_id})
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    return _serialize(org)


@router.patch("/me")
async def update_my_organization(payload: OrgSettingsUpdate, user: dict = Depends(_require_org_owner)):
    updates = {k: v for k, v in payload.model_dump().items() if v is not None or k == "smsNumber"}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    org_id = user["orgId"]
    query_id = ObjectId(org_id) if ObjectId.is_valid(org_id) else org_id

    # A real, cross-org uniqueness check - two organizations must
    # never both claim the same Twilio number, or inbound texts to it
    # would be ambiguous about which org they belong to.
    if updates.get("smsNumber"):
        existing = await organizations_col.find_one({"smsNumber": updates["smsNumber"], "_id": {"$ne": query_id}})
        if existing:
            raise HTTPException(status_code=409, detail="This phone number is already configured for a different organization.")

    result = await organizations_col.find_one_and_update(
        {"_id": query_id}, {"$set": updates}, return_document=True
    )
    if not result:
        raise HTTPException(status_code=404, detail="Organization not found")
    return _serialize(result)
