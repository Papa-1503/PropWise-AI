"""
Auth endpoints.

POST /api/auth/register         -> create an account. SECURITY: always
                                    creates a "tenant" role, regardless of
                                    what the client requests. If propertyId
                                    and unitId are provided, they are only
                                    honored if a lease exists matching that
                                    property/unit with residentEmail equal
                                    to the registering email — see the
                                    security note below.
POST /api/auth/register-staff   -> create a staff account. Requires an
                                    existing staff member's token — this
                                    is how you provision additional staff
                                    users, not through public registration.
POST /api/auth/login            -> returns a JWT + user profile
GET  /api/auth/me               -> current user, given a valid Bearer token

SECURITY NOTES (both found in live-testing passes, both fixed here):

1. The original version passed the client-supplied `role` field straight
   to the database on the public /register endpoint, so anyone could
   self-register with {"role": "staff"} and get full staff access.
   /register now hardcodes role="tenant" unconditionally.

2. Even after fixing (1), /register still let a client supply ANY
   propertyId/unitId with no verification — meaning anyone (including
   multiple different people simultaneously) could self-register
   claiming to live in any unit, and payments.py / maintenance.py both
   scope tenant access by that self-reported propertyId/unitId. This
   was confirmed live: two different accounts both successfully claimed
   the same unit and both got 200 OK access to that unit's data.
   Fixed: propertyId/unitId are now only attached to the account if a
   lease already exists (created by staff) with a matching
   propertyId + unitId + residentEmail. Otherwise the account is still
   created — so registration itself doesn't fail — but with no unit
   binding, meaning it has no access to any unit's payments or tickets
   until staff creates a matching lease record for that email.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends
from pymongo.errors import DuplicateKeyError

from db import users_col, leases_col
from models import UserRegister, UserLogin, TokenResponse, UserOut
from auth import hash_password, verify_password, create_access_token, get_current_user, require_staff

router = APIRouter(prefix="/api/auth", tags=["auth"])


def to_user_out(user: dict) -> UserOut:
    return UserOut(
        id=user["id"] if "id" in user else str(user["_id"]),
        email=user["email"],
        name=user["name"],
        role=user["role"],
        propertyId=user.get("propertyId"),
        unitId=user.get("unitId"),
    )


async def _create_user(payload: UserRegister, forced_role: str | None = None, verify_unit: bool = False) -> TokenResponse:
    """Shared creation logic.

    forced_role: if set, overrides whatever role was in the request payload.
    verify_unit: if True (used on the public /register path), propertyId/
    unitId are only kept if a matching lease record exists for this email —
    otherwise they're silently dropped so the account has no unit access.
    """
    doc = payload.model_dump()
    if forced_role is not None:
        doc["role"] = forced_role

    if verify_unit and doc.get("propertyId") and doc.get("unitId"):
        matching_lease = await leases_col.find_one({
            "propertyId": doc["propertyId"],
            "unitId": doc["unitId"],
            "residentEmail": doc["email"],
        })
        if not matching_lease:
            doc["propertyId"] = None
            doc["unitId"] = None

    doc["password"] = hash_password(doc.pop("password"))
    doc["createdAt"] = datetime.now(timezone.utc)
    try:
        result = await users_col.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    doc["id"] = str(result.inserted_id)
    token = create_access_token(doc["id"], doc["role"])
    return TokenResponse(accessToken=token, user=to_user_out(doc))


@router.post("/register", response_model=TokenResponse)
async def register(payload: UserRegister):
    # SECURITY: force tenant role, and only bind to a unit if a matching
    # lease record proves this email actually belongs to that unit's
    # resident. See module docstring.
    return await _create_user(payload, forced_role="tenant", verify_unit=True)


@router.post("/register-staff", response_model=TokenResponse)
async def register_staff(payload: UserRegister, current_user: dict = Depends(require_staff)):
    """Only an already-authenticated staff member can create another staff account."""
    return await _create_user(payload, forced_role="staff")


@router.post("/login", response_model=TokenResponse)
async def login(payload: UserLogin):
    user = await users_col.find_one({"email": payload.email})
    if not user or not verify_password(payload.password, user["password"]):
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    user["id"] = str(user["_id"])
    token = create_access_token(user["id"], user["role"])
    return TokenResponse(accessToken=token, user=to_user_out(user))


@router.get("/me", response_model=UserOut)
async def me(user: dict = Depends(get_current_user)):
    return to_user_out(user)
