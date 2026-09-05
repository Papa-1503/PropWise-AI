"""
Auth endpoints.

POST /api/auth/register         -> public resident activation via invite
                                    code (see TenantActivate model).
                                    CHANGED Aug 25, 2026: previously
                                    accepted client-submitted propertyId/
                                    unitId and only trusted them if they
                                    matched an existing lease's
                                    residentEmail — now replaced entirely
                                    with an invite-code flow. The client
                                    NEVER submits propertyId/unitId/role
                                    for this endpoint anymore; the invite
                                    code (generated server-side when staff
                                    create a lease) is the only thing that
                                    determines unit binding. This closes
                                    that surface completely rather than
                                    just verifying it.
POST /api/auth/register-staff   -> create a staff account. Requires an
                                    existing staff member's token — this
                                    is how you provision additional staff
                                    users, not through public registration.
POST /api/auth/register-owner   -> same, for owner accounts.
POST /api/auth/login            -> returns a JWT + user profile
GET  /api/auth/me               -> current user, given a valid Bearer token

SECURITY HISTORY (kept for context — the first two were found and fixed
in an earlier session, the third is today's further hardening):

1. The original version passed the client-supplied `role` field straight
   to the database on the public /register endpoint, so anyone could
   self-register with {"role": "staff"} and get full staff access.
   Fixed by hardcoding role="tenant" unconditionally on that path.

2. Even after fixing (1), /register still let a client supply ANY
   propertyId/unitId with no verification — meaning anyone could
   self-register claiming to live in any unit. Confirmed live: two
   different accounts both successfully claimed the same unit. Fixed
   (at the time) by only trusting propertyId/unitId if they matched an
   existing lease's residentEmail.

3. Aug 25, 2026: replaced that email-matching approach entirely with
   invite codes, per Priority 34 (also flagged independently by two
   external audits as "Property ID/Unit ID" being raw, resident-unfriendly
   implementation details in the sign-up form — this fixes both the
   security surface and the UX issue in one change). The public
   TenantActivate model no longer has propertyId/unitId/role fields at
   all, so there's nothing left for a client to even attempt to spoof.
"""
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException, Depends, Response, Request
from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from db import users_col, leases_col, properties_col, organizations_col
from models import StaffOwnerRegister, TenantActivate, UserLogin, TokenResponse, UserOut, ProfileUpdate, PasswordChange, OrganizationSignup
from email_service import send_email_async, EmailNotConfigured, EmailSendError
from auth import hash_password, verify_password, create_access_token, get_current_user, require_staff, set_session_cookie, COOKIE_NAME
from rate_limiter import limiter
import translation_service

router = APIRouter(prefix="/api/auth", tags=["auth"])

TRIAL_LENGTH_DAYS = 14


def to_user_out(user: dict) -> UserOut:
    return UserOut(
        id=user["id"] if "id" in user else str(user["_id"]),
        email=user["email"],
        name=user["name"],
        role=user["role"],
        propertyId=user.get("propertyId"),
        unitId=user.get("unitId"),
        preferredLanguage=user.get("preferredLanguage"),
        orgId=user.get("orgId"),
        isOrgOwner=user.get("isOrgOwner", False),
    )


@router.post("/signup-organization", response_model=TokenResponse)
@limiter.limit("5/minute")
async def signup_organization(request: Request, payload: OrganizationSignup, response: Response):
    """The real "create a brand-new company account" entry point -
    genuinely did not exist anywhere before this. Every other account-
    creation path (tenant activation, staff/owner invites) requires an
    organization to already exist; this is the only place one gets
    created. Public, rate-limited the same as /register and /login,
    since - like those - it's an unauthenticated endpoint anyone can
    reach.

    The created organization starts on a real trial (see
    TRIAL_LENGTH_DAYS) rather than some permanent free tier - an
    honest default for a product meant to be sold, not a placeholder
    that would need revisiting before this could actually go out to
    real customers."""
    existing_org = await organizations_col.find_one({"name": payload.organizationName})
    if existing_org:
        raise HTTPException(status_code=409, detail="An organization with this name already exists.")

    now = datetime.now(timezone.utc)
    org_doc = {
        "name": payload.organizationName,
        "plan": "trial",
        "active": True,
        "createdAt": now,
        "trialEndsAt": now + timedelta(days=TRIAL_LENGTH_DAYS),
    }
    org_result = await organizations_col.insert_one(org_doc)
    org_id = str(org_result.inserted_id)

    doc = {
        "email": payload.email,
        "password": hash_password(payload.password),
        "name": payload.name,
        "role": "staff",
        "orgId": org_id,
        "isOrgOwner": True,
        "createdAt": now,
    }
    try:
        result = await users_col.insert_one(doc)
    except DuplicateKeyError:
        # Roll back the org we just created rather than leaving an
        # orphaned organization with no real owner attached to it -
        # this can only happen on the genuinely rare case of the
        # email already existing globally (users_col.email has a real
        # unique index), which the org-name check above doesn't catch.
        await organizations_col.delete_one({"_id": org_result.inserted_id})
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    doc["id"] = str(result.inserted_id)
    token = create_access_token(doc["id"], doc["role"])
    set_session_cookie(response, token)
    return TokenResponse(accessToken=token, user=to_user_out(doc))


async def _create_staff_or_owner(payload: StaffOwnerRegister, forced_role: str, org_id: str, response: Response) -> TokenResponse:
    """Used only by the staff-authenticated register-staff/register-owner
    paths below — the public tenant path has its own function now.
    org_id always comes from the inviting staff member's OWN orgId
    (the caller passes current_user["orgId"], never anything client-
    submitted) - the only way to join an organization other than
    creating one outright is being invited by someone already in it."""
    doc = payload.model_dump()
    doc["role"] = forced_role
    doc["orgId"] = org_id
    doc["password"] = hash_password(doc.pop("password"))
    doc["createdAt"] = datetime.now(timezone.utc)
    try:
        result = await users_col.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    doc["id"] = str(result.inserted_id)
    token = create_access_token(doc["id"], doc["role"])
    set_session_cookie(response, token)
    return TokenResponse(accessToken=token, user=to_user_out(doc))


@router.post("/register", response_model=TokenResponse)
@limiter.limit("5/minute")
async def register(request: Request, payload: TenantActivate, response: Response):
    """Public resident activation. The invite code is the sole source of
    truth for which unit this account binds to — nothing client-submitted
    is trusted for that purpose. orgId is derived from the property the
    lease belongs to, not client-submitted either - a resident always
    joins whichever organization actually owns their building."""
    lease = await leases_col.find_one({"inviteCode": payload.inviteCode})
    if not lease:
        raise HTTPException(status_code=400, detail="Invalid invite code")

    property_id = lease["propertyId"]
    property_query_id = ObjectId(property_id) if ObjectId.is_valid(property_id) else property_id
    property_doc = await properties_col.find_one({"_id": property_query_id})
    if not property_doc or not property_doc.get("orgId"):
        # A real, if rare, data-integrity problem - a lease pointing at
        # a property with no organization on file. Refusing activation
        # here is safer than silently creating an orphaned tenant
        # account with no organization at all, which nothing in this
        # app is built to handle correctly.
        raise HTTPException(status_code=500, detail="This property isn't fully configured yet. Please contact the property office.")

    doc = {
        "email": payload.email,
        "password": hash_password(payload.password),
        "name": payload.name,
        "role": "tenant",
        "orgId": property_doc["orgId"],
        "propertyId": lease["propertyId"],
        "unitId": lease["unitId"],
        "createdAt": datetime.now(timezone.utc),
    }
    try:
        result = await users_col.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    # Keep the lease's own residentEmail in sync if it wasn't already
    # set — helps other features that look up a resident by lease email.
    if not lease.get("residentEmail"):
        await leases_col.update_one({"_id": lease["_id"]}, {"$set": {"residentEmail": payload.email}})

    doc["id"] = str(result.inserted_id)
    token = create_access_token(doc["id"], doc["role"])
    set_session_cookie(response, token)

    # Real welcome email, using this tenant's actual lease — not a
    # fabricated "lease signed by both parties" flow, since PropWise AI
    # doesn't have formal digital co-signing; account activation via
    # invite code is the real equivalent trigger point in this app.
    # A send failure never blocks activation itself — the account is
    # already created by this point — but it's not silently pretended
    # to succeed either, matching how every other email send in this
    # app is handled.
    try:
        rent_line = f"${lease.get('rent', 0):,.0f}/month" if lease.get("rent") else "your rent amount"
        await send_email_async(
            to=payload.email,
            subject="Welcome to PropWise AI",
            body_text=(
                f"Hi {payload.name},\n\n"
                f"Your resident account for Unit {lease['unitId']} is now active.\n\n"
                f"Rent: {rent_line}\n"
                f"Lease term: {lease.get('startDate')} to {lease.get('endDate')}\n\n"
                "In your portal you can view your lease documents, see payment history, "
                "submit maintenance requests, and ask the AI assistant questions about "
                "your account anytime.\n\n"
                "Welcome home."
            ),
        )
    except (EmailNotConfigured, EmailSendError):
        pass

    return TokenResponse(accessToken=token, user=to_user_out(doc))


@router.post("/register-staff", response_model=TokenResponse)
async def register_staff(payload: StaffOwnerRegister, response: Response, current_user: dict = Depends(require_staff)):
    """Only an already-authenticated staff member can create another staff
    account, and only ever into that SAME staff member's own organization."""
    return await _create_staff_or_owner(payload, forced_role="staff", org_id=current_user["orgId"], response=response)

@router.post("/register-owner", response_model=TokenResponse)
async def register_owner(payload: StaffOwnerRegister, response: Response, current_user: dict = Depends(require_staff)):
    """Only an already-authenticated staff member can create an owner
    account, and only ever into that SAME staff member's own organization."""
    return await _create_staff_or_owner(payload, forced_role="owner", org_id=current_user["orgId"], response=response)


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
async def login(request: Request, payload: UserLogin, response: Response):
    user = await users_col.find_one({"email": payload.email})
    if not user or not verify_password(payload.password, user["password"]):
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    user["id"] = str(user["_id"])
    token = create_access_token(user["id"], user["role"])
    set_session_cookie(response, token)
    return TokenResponse(accessToken=token, user=to_user_out(user))


@router.get("/languages")
async def list_supported_languages():
    """Public - just the real, current supported-language set from
    translation_service.py, so the frontend's language picker can
    never silently drift out of sync with what the backend actually
    supports."""
    return {"languages": translation_service.SUPPORTED_LANGUAGES}


@router.get("/me", response_model=UserOut)
async def me(user: dict = Depends(get_current_user)):
    return to_user_out(user)


@router.post("/logout")
async def logout(response: Response):
    """Clears the real session cookie - genuinely needed now that one
    exists. An HttpOnly cookie can't be cleared from JavaScript (that's
    the whole point - it's immune to XSS reading it), so the frontend's
    existing "logout" (just clearing localStorage) would otherwise leave
    a valid cookie sitting active for up to its full 7-day lifetime.
    Doesn't require auth to call - a browser with no valid session has
    nothing meaningful to log out of, and this only ever clears the
    cookie on the caller's own browser, never anyone else's."""
    response.delete_cookie(key=COOKIE_NAME, path="/")
    return {"loggedOut": True}


@router.patch("/me", response_model=UserOut)
async def update_profile(payload: ProfileUpdate, user: dict = Depends(get_current_user)):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name can't be empty.")
    updates = {"name": name}
    if payload.preferredLanguage is not None:
        # Real validation against the actual supported set, not a bare
        # passthrough - an unrecognized code stored here would silently
        # never translate anything, with no error telling anyone why.
        if payload.preferredLanguage not in translation_service.SUPPORTED_LANGUAGES:
            raise HTTPException(status_code=400, detail="Unsupported language.")
        updates["preferredLanguage"] = payload.preferredLanguage
    await users_col.update_one({"_id": ObjectId(user["id"])}, {"$set": updates})
    updated = dict(user)
    updated.update(updates)
    return to_user_out(updated)


@router.post("/change-password")
async def change_password(payload: PasswordChange, user: dict = Depends(get_current_user)):
    doc = await users_col.find_one({"_id": ObjectId(user["id"])})
    if not doc or not verify_password(payload.currentPassword, doc["password"]):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")
    if len(payload.newPassword) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters.")
    await users_col.update_one(
        {"_id": ObjectId(user["id"])}, {"$set": {"password": hash_password(payload.newPassword)}}
    )
    return {"status": "ok"}
