"""
Auth core: password hashing, JWT issue/verify, and FastAPI dependencies
for protecting routes by login state and by role (staff vs tenant).

Requires: pip install bcrypt PyJWT python-multipart
Set JWT_SECRET in your environment in production — the default below
is only for local dev and is NOT safe to ship.

CHANGED (Sept 2, 2026): swapped python-jose for PyJWT. python-jose
carries a real, current CVE (CVE-2025-61152 — a forged token with
alg=none bypasses signature verification entirely, confirmed via a
direct search, not assumed) plus several older, real CVEs against its
bundled ecdsa dependency that its maintainers have stated they don't
plan to fix. This app's own decode call already specified an explicit
algorithms=[JWT_ALGORITHM] allowlist, which defends against the worst
(alg=none) exploit path regardless of library — so this wasn't
actively exploitable here — but continuing to depend on an
unmaintained library with open, unfixed CVEs is a real, avoidable
supply-chain risk worth removing outright, not just working around.
PyJWT is the more actively maintained, more widely used library for
this exact use case. The only real API difference for how this file
uses it: the exception type changes from jose.JWTError to
jwt.PyJWTError (or its subclasses like ExpiredSignatureError) — encode/
decode call shapes are otherwise identical.
"""
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
import jwt
from jwt import PyJWTError
import bcrypt
from bson import ObjectId

from db import users_col, custom_roles_col

JWT_SECRET = os.getenv("JWT_SECRET", "dev-only-secret-change-me")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def hash_password(password: str) -> str:
    # bcrypt has a hard 72-byte input limit (a library constraint, not a
    # design choice here) — truncate defensively rather than letting an
    # unusually long password raise an unhandled error at registration.
    pw_bytes = password.encode("utf-8")[:72]
    return bcrypt.hashpw(pw_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8")[:72], hashed.encode("utf-8"))


def create_access_token(user_id: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": user_id, "role": role, "exp": expire}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


COOKIE_NAME = "rentflow_session"


async def get_current_user(request: Request, token: Optional[str] = Depends(oauth2_scheme)) -> dict:
    """Accepts EITHER an Authorization: Bearer header (the existing,
    unchanged flow every current frontend call still uses) OR a real
    HttpOnly session cookie (COOKIE_NAME, set by login/register - see
    routers/auth.py) - whichever is present. This is a deliberately
    backward-compatible transition, not a hard cutover: the existing
    localStorage-token flow keeps working exactly as it does today
    (nothing about it changes), while the strictly more secure cookie
    path (immune to XSS token theft in a way localStorage never was,
    since JavaScript can't read an HttpOnly cookie at all) becomes
    available immediately. A full migration away from the header flow
    entirely - updating every frontend authFetch call - is real,
    separate follow-on work, not bundled into this change."""
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise unauthorized
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            raise unauthorized
    except PyJWTError:
        raise unauthorized

    user = await users_col.find_one({"_id": ObjectId(user_id)})
    if not user:
        raise unauthorized
    user["id"] = str(user.pop("_id"))
    return user


def require_role(*allowed_roles: str):
    """Use as a dependency: Depends(require_role('staff'))"""

    async def checker(user: dict = Depends(get_current_user)) -> dict:
        if user["role"] not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires role: {' or '.join(allowed_roles)}",
            )
        return user

    return checker


def require_permission(permission: str):
    """A genuinely additive second authorization mechanism, not a
    replacement for require_role - see CustomRoleCreate's docstring in
    models.py for the full reasoning. A staff user with NO custom role
    assigned (customRoleId is None/absent on their user record, the
    default for every existing account and every account created
    without explicitly assigning one) is granted every permission -
    exactly today's real behavior, since role='staff' alone currently
    means full access everywhere. A staff user WITH a custom role
    assigned is scoped to exactly that role's real permission list,
    checked here. A non-staff role (tenant/owner) is always rejected,
    same as require_staff already does - this dependency is a finer-
    grained check within staff access, not a way around the existing
    role boundary."""

    async def checker(user: dict = Depends(get_current_user)) -> dict:
        if user["role"] != "staff":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Requires role: staff")
        custom_role_id = user.get("customRoleId")
        if not custom_role_id:
            return user  # no custom role assigned - full access, today's real default behavior
        if not ObjectId.is_valid(custom_role_id):
            return user  # a malformed stored value should never itself become a lockout
        role_doc = await custom_roles_col.find_one({"_id": ObjectId(custom_role_id)})
        if not role_doc or permission not in role_doc.get("permissions", []):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Your role does not include '{permission}' access.",
            )
        return user

    return checker


# Convenience dependencies for the common cases
require_staff = require_role("staff")
require_owner = require_role("owner")
require_staff_or_owner = require_role("staff", "owner")
require_any_authenticated = get_current_user


def set_session_cookie(response, token: str) -> None:
    """Sets the real HttpOnly session cookie alongside the existing
    Bearer-token response body - see get_current_user's docstring for
    why this is additive, not a replacement. SameSite=None (not the
    more common Lax) is a deliberate, necessary choice here, not an
    oversight: the frontend (rentflow-ai-1.onrender.com) and backend
    (rentflow-ai.onrender.com) are genuinely different origins, not
    same-site variants - SameSite=Lax would silently block this cookie
    from ever being sent on the frontend's cross-origin API calls,
    making the whole cookie pointless. SameSite=None requires
    Secure=True together (browsers reject the combination otherwise),
    which is correctly satisfied here since both are real HTTPS
    origins already."""
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=True,
        secure=True,
        samesite="none",
        path="/",
    )
