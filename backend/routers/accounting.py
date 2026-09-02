"""
QuickBooks Online accounting sync — real OAuth2 connect flow + one real
sync operation (pushing a received rent payment into QuickBooks as a
real Payment against a matched/created Customer). See
quickbooks_service.py's own docstring for the required environment
variables and what's genuinely NOT built yet (bills/expenses/full
bidirectional sync).

GET  /api/accounting/connect              -> (staff) returns the real Intuit
                                              authorization URL to redirect to
GET  /api/accounting/callback              -> PUBLIC (Intuit redirects the
                                              browser here after approval) —
                                              exchanges the code for real tokens
GET  /api/accounting/status                -> (staff) connected? which company?
POST /api/accounting/sync-payment/{charge_id} -> (staff) push one payment to QuickBooks
POST /api/accounting/disconnect            -> (staff) clears the stored connection

Single connection for the whole app, not per-property — matches how a
real property management company almost always runs one QuickBooks
company file for its whole operation, categorizing by property/class
within it rather than maintaining a separate QuickBooks company per
building.
"""
import os
import secrets
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import RedirectResponse
from bson import ObjectId

from db import accounting_connections_col, payments_col, leases_col
from auth import require_staff
from audit_service import log_action
import quickbooks_service
from quickbooks_service import QuickBooksNotConfigured, QuickBooksApiError

router = APIRouter(prefix="/api/accounting", tags=["accounting"])


async def _get_connection() -> dict | None:
    return await accounting_connections_col.find_one({"provider": "quickbooks"})


async def _get_valid_access_token(connection: dict) -> str:
    """Returns a real, currently-valid access token — refreshing first
    if the stored one has actually expired. Persists BOTH the new
    access token and the new refresh token immediately (see
    quickbooks_service.py's own docstring on why the refresh token
    specifically must never be left stale)."""
    expires_at = connection.get("tokenExpiresAt")
    now = datetime.now(timezone.utc)
    # 5-minute safety buffer before the real expiry, not right at the edge
    if expires_at and isinstance(expires_at, datetime) and expires_at.replace(tzinfo=timezone.utc) > now + timedelta(minutes=5):
        return connection["accessToken"]

    result = await quickbooks_service.refresh_access_token_async(connection["refreshToken"])
    new_access_token = result["access_token"]
    new_refresh_token = result["refresh_token"]  # a genuinely NEW token, not the same one
    new_expires_at = now + timedelta(seconds=result.get("expires_in", 3600))

    await accounting_connections_col.update_one(
        {"provider": "quickbooks"},
        {"$set": {"accessToken": new_access_token, "refreshToken": new_refresh_token, "tokenExpiresAt": new_expires_at}},
    )
    return new_access_token


@router.get("/connect")
async def connect(user: dict = Depends(require_staff)):
    """Step 1: generates a real, per-attempt CSRF state token, stores
    it, and returns the real Intuit authorization URL to send the
    staff member to."""
    try:
        state = secrets.token_urlsafe(32)
        await accounting_connections_col.update_one(
            {"provider": "quickbooks"},
            {"$set": {"provider": "quickbooks", "pendingState": state, "pendingStateCreatedAt": datetime.now(timezone.utc)}},
            upsert=True,
        )
        auth_url = quickbooks_service.get_authorization_url(state)
    except QuickBooksNotConfigured as exc:
        raise HTTPException(status_code=501, detail=str(exc))
    return {"authorizationUrl": auth_url}


@router.get("/callback")
async def callback(request: Request, code: str | None = None, state: str | None = None, realmId: str | None = None):
    """Step 2/3: Intuit redirects the browser here after the staff
    member approves access, with a real authorization code, the same
    state this app generated in /connect, and the real realmId
    (QuickBooks company ID). Deliberately public — Intuit's redirect
    is a plain browser navigation, not an authenticated API call — the
    state check is what actually prevents a forged callback from
    completing a connection."""
    if not code or not state or not realmId:
        raise HTTPException(status_code=400, detail="Missing code, state, or realmId from QuickBooks' redirect.")

    connection = await _get_connection()
    if not connection or connection.get("pendingState") != state:
        raise HTTPException(status_code=403, detail="Invalid or expired state — start the connect flow again.")

    try:
        tokens = await quickbooks_service.exchange_code_for_tokens_async(code)
    except (QuickBooksNotConfigured, QuickBooksApiError) as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    now = datetime.now(timezone.utc)
    await accounting_connections_col.update_one(
        {"provider": "quickbooks"},
        {"$set": {
            "realmId": realmId,
            "accessToken": tokens["access_token"],
            "refreshToken": tokens["refresh_token"],
            "tokenExpiresAt": now + timedelta(seconds=tokens.get("expires_in", 3600)),
            "connectedAt": now,
        }, "$unset": {"pendingState": "", "pendingStateCreatedAt": ""}},
    )
    return RedirectResponse(url="/app/reconciliation?quickbooksConnected=true")


@router.get("/status")
async def status(user: dict = Depends(require_staff)):
    connection = await _get_connection()
    if not connection or not connection.get("realmId"):
        return {"connected": False}
    return {
        "connected": True,
        "realmId": connection["realmId"],
        "connectedAt": connection["connectedAt"].isoformat() if isinstance(connection.get("connectedAt"), datetime) else None,
        "sandbox": os.getenv("QUICKBOOKS_SANDBOX", "false").lower() == "true",
    }


@router.post("/sync-payment/{charge_id}")
async def sync_payment(charge_id: str, user: dict = Depends(require_staff)):
    """Pushes one already-recorded payment (see routers/payments.py)
    into QuickBooks as a real Payment against a matched/created
    Customer — the actual, real sync operation this infrastructure is
    for. Fails honest at every real failure point (not connected,
    charge not found/not actually paid, no resident name to match a
    customer against) rather than silently doing nothing."""
    connection = await _get_connection()
    if not connection or not connection.get("realmId"):
        raise HTTPException(status_code=501, detail="QuickBooks isn't connected yet — call GET /api/accounting/connect first.")

    if not ObjectId.is_valid(charge_id):
        raise HTTPException(status_code=400, detail="Invalid charge ID")
    charge = await payments_col.find_one({"_id": ObjectId(charge_id)})
    if not charge:
        raise HTTPException(status_code=404, detail="Charge not found")
    amount_paid = charge.get("amountPaid", 0)
    if amount_paid <= 0:
        raise HTTPException(status_code=400, detail="This charge has no payment recorded against it yet.")
    if charge.get("quickbooksPaymentId"):
        raise HTTPException(status_code=400, detail="This payment was already synced to QuickBooks.")

    lease = await leases_col.find_one({"propertyId": charge.get("propertyId"), "unitId": charge.get("unitId")})
    resident_name = lease.get("residentName") if lease else None
    if not resident_name:
        raise HTTPException(status_code=400, detail="No resident name on file for this unit — can't match a QuickBooks customer.")

    try:
        access_token = await _get_valid_access_token(connection)
        customer_id = await quickbooks_service.find_or_create_customer_async(
            access_token, connection["realmId"], resident_name, lease.get("residentEmail"),
        )
        result = await quickbooks_service.record_payment_async(
            access_token, connection["realmId"], customer_id, amount_paid,
            memo=f"{charge.get('description', 'Rent payment')} — Unit {charge.get('unitId')}",
        )
    except (QuickBooksNotConfigured, QuickBooksApiError) as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    qb_payment_id = result.get("Payment", {}).get("Id")
    await payments_col.update_one(
        {"_id": ObjectId(charge_id)},
        {"$set": {"quickbooksPaymentId": qb_payment_id, "quickbooksSyncedAt": datetime.now(timezone.utc)}},
    )

    await log_action(
        actor_id=str(user["id"]), actor_email=user.get("email", ""),
        action="quickbooks_payment_synced", target_type="payment", target_id=charge_id,
        details={"quickbooksPaymentId": qb_payment_id, "amount": amount_paid},
    )

    return {"synced": True, "quickbooksPaymentId": qb_payment_id}


@router.post("/disconnect")
async def disconnect(user: dict = Depends(require_staff)):
    await accounting_connections_col.delete_one({"provider": "quickbooks"})
    await log_action(
        actor_id=str(user["id"]), actor_email=user.get("email", ""),
        action="quickbooks_disconnected", target_type="accounting_connection", target_id="quickbooks",
        details={},
    )
    return {"connected": False}
