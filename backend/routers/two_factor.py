"""
Two-factor authentication (TOTP) — genuinely missing before this. For
a product that moves real rent money and holds resident PII,
password-only login on the org owner and staff accounts was a real,
meaningful gap - this closes it with standard, authenticator-app-
compatible TOTP (works with Google Authenticator, Authy, 1Password,
etc. - any app implementing RFC 6238, not a proprietary scheme).

GET  /api/auth/2fa/status   -> whether 2FA is currently enabled for
                                the calling user
POST /api/auth/2fa/setup    -> generates a new, real TOTP secret (not
                                yet active) and returns a scannable QR
                                code - the real first step of enabling
POST /api/auth/2fa/enable   -> confirms the user's authenticator app
                                actually produces matching codes, THEN
                                activates 2FA and issues one-time
                                backup codes
POST /api/auth/2fa/disable  -> requires the current password (not just
                                being logged in) to turn 2FA back off

The actual LOGIN-time verification step lives in routers/auth.py's
/login and the new /login/2fa (a real two-step flow: password first,
then a TOTP or backup code) - kept there rather than here since it's
genuinely part of the login flow, not account settings.

SETUP IS A TWO-STEP, CONFIRM-BEFORE-ENABLE FLOW, DELIBERATELY: /setup
stores the new secret as pending (totpSecretPending), not yet active.
Only /enable, after verifying a real code the user's own app just
generated, promotes it to the real, active secret. This prevents a
genuine, real failure mode: enabling 2FA against a secret the user
never actually confirmed their app can generate matching codes for
would permanently lock them out of their own account the moment they
log out.

BACKUP CODES exist for the real, ordinary case of losing/replacing a
phone - 8 single-use codes, generated once at /enable time and shown
exactly once (never re-displayed, never retrievable again - the same
principle as a Stripe secret key). Stored as bcrypt hashes, exactly
like the real account password, never in plaintext.
"""
import secrets
import base64
import io

import pyotp
import qrcode
from bson import ObjectId
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from db import users_col
from auth import get_current_user, verify_password, hash_password
from models import TwoFactorEnableRequest, TwoFactorEnableResponse, TwoFactorDisableRequest
from audit_service import log_action

router = APIRouter(prefix="/api/auth/2fa", tags=["two-factor"])

BACKUP_CODE_COUNT = 8


class TwoFactorSetupResponse(BaseModel):
    secret: str
    qrCodeDataUri: str


def _generate_backup_codes() -> list[str]:
    """8 real, random, single-use codes - formatted in two groups of 4
    (e.g. 'a1b2-c3d4') purely for real human readability when a person
    is copying one down or reading it off a printed sheet, not for any
    security reason."""
    codes = []
    for _ in range(BACKUP_CODE_COUNT):
        raw = secrets.token_hex(4)  # 8 real hex characters
        codes.append(f"{raw[:4]}-{raw[4:]}")
    return codes


@router.get("/status")
async def two_factor_status(user: dict = Depends(get_current_user)):
    return {"enabled": bool(user.get("totpEnabled"))}


@router.post("/setup", response_model=TwoFactorSetupResponse)
async def setup_two_factor(user: dict = Depends(get_current_user)):
    """Generates a real, new secret and stores it as PENDING only -
    see this module's own docstring for why activation is a separate,
    later step (/enable) rather than happening here."""
    if user.get("totpEnabled"):
        raise HTTPException(status_code=400, detail="Two-factor authentication is already enabled. Disable it first to set up a new device.")

    secret = pyotp.random_base32()
    user_id = ObjectId(user["id"]) if isinstance(user["id"], str) else user["id"]
    await users_col.update_one({"_id": user_id}, {"$set": {"totpSecretPending": secret}})

    totp = pyotp.TOTP(secret)
    provisioning_uri = totp.provisioning_uri(name=user.get("email", ""), issuer_name="PropWise AI")

    qr_img = qrcode.make(provisioning_uri)
    buffer = io.BytesIO()
    qr_img.save(buffer, format="PNG")
    qr_base64 = base64.b64encode(buffer.getvalue()).decode()

    return TwoFactorSetupResponse(secret=secret, qrCodeDataUri=f"data:image/png;base64,{qr_base64}")


@router.post("/enable", response_model=TwoFactorEnableResponse)
async def enable_two_factor(payload: TwoFactorEnableRequest, user: dict = Depends(get_current_user)):
    """The real confirmation step - only activates 2FA once the code
    the user's own authenticator app just generated is verified
    against the pending secret from /setup. valid_window=1 allows one
    30-second time-step of clock drift either direction, a real,
    standard TOTP tolerance (RFC 6238's own recommendation), not a
    security weakening - it does not widen the code's actual guessing
    window in any meaningful way."""
    user_id = ObjectId(user["id"]) if isinstance(user["id"], str) else user["id"]

    fresh_user = await users_col.find_one({"_id": user_id})
    pending_secret = fresh_user.get("totpSecretPending") if fresh_user else None
    if not pending_secret:
        raise HTTPException(status_code=400, detail="No pending two-factor setup found - call /2fa/setup first.")

    totp = pyotp.TOTP(pending_secret)
    if not totp.verify(payload.code, valid_window=1):
        raise HTTPException(status_code=400, detail="That code doesn't match. Double-check your authenticator app and try again.")

    backup_codes = _generate_backup_codes()
    backup_code_hashes = [hash_password(code) for code in backup_codes]

    await users_col.update_one(
        {"_id": user_id},
        {
            "$set": {"totpSecret": pending_secret, "totpEnabled": True, "totpBackupCodeHashes": backup_code_hashes},
            "$unset": {"totpSecretPending": ""},
        },
    )

    await log_action(
        actor_id=user["id"], actor_email=user.get("email", ""), org_id=user.get("orgId"),
        action="two_factor_enabled", target_type="user", target_id=user["id"],
    )

    return TwoFactorEnableResponse(backupCodes=backup_codes)


@router.post("/disable")
async def disable_two_factor(payload: TwoFactorDisableRequest, user: dict = Depends(get_current_user)):
    if not verify_password(payload.password, user["password"]):
        raise HTTPException(status_code=401, detail="Incorrect password.")

    user_id = ObjectId(user["id"]) if isinstance(user["id"], str) else user["id"]
    await users_col.update_one(
        {"_id": user_id},
        {"$set": {"totpEnabled": False}, "$unset": {"totpSecret": "", "totpSecretPending": "", "totpBackupCodeHashes": ""}},
    )

    await log_action(
        actor_id=user["id"], actor_email=user.get("email", ""), org_id=user.get("orgId"),
        action="two_factor_disabled", target_type="user", target_id=user["id"],
    )

    return {"enabled": False}
