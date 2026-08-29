"""
Auth core: password hashing, JWT issue/verify, and FastAPI dependencies
for protecting routes by login state and by role (staff vs tenant).

Requires: pip install bcrypt python-jose python-multipart
Set JWT_SECRET in your environment in production — the default below
is only for local dev and is NOT safe to ship.
"""
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
import bcrypt
from bson import ObjectId

from db import users_col

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


async def get_current_user(token: Optional[str] = Depends(oauth2_scheme)) -> dict:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise unauthorized
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            raise unauthorized
    except JWTError:
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


# Convenience dependencies for the common cases
require_staff = require_role("staff")
require_owner = require_role("owner")
require_staff_or_owner = require_role("staff", "owner")
require_any_authenticated = get_current_user
