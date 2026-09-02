"""
QuickBooks Online accounting sync — real OAuth2 infrastructure, usable
the moment QUICKBOOKS_CLIENT_ID/QUICKBOOKS_CLIENT_SECRET are configured
and a staff member completes the one-time "Connect to QuickBooks" flow
(see routers/accounting.py). Built directly from Intuit's own current
(2026) API documentation — real endpoints, real OAuth2 flow, real
entity shapes — not guessed.

Required environment variables:
    QUICKBOOKS_CLIENT_ID       — from a real app registered at
                                  developer.intuit.com (free account)
    QUICKBOOKS_CLIENT_SECRET
    QUICKBOOKS_REDIRECT_URI    — must exactly match what's registered
                                  in the Intuit app's settings, e.g.
                                  https://rentflow-ai.onrender.com/api/accounting/callback
    QUICKBOOKS_SANDBOX         — "true" to use Intuit's sandbox company
                                  (free, pre-loaded with test data) while
                                  developing; unset or "false" for a
                                  real production QuickBooks company

QuickBooksNotConfigured: the app-level credentials aren't set, or no
    company has completed the connect flow yet.
QuickBooksApiError: a real API call failed — expired/invalid token,
    Intuit-side error, a rejected entity, etc.

Genuinely different from Stripe/Twilio/RentCast/Seam in one important
way: those all use a single static secret key. QuickBooks is OAuth2
with an access token that expires every 60 minutes and a refresh token
that ROTATES on every use — Intuit issues a brand-new refresh token
each time you refresh, and the previous one stops working. The caller
(routers/accounting.py) MUST persist the new refresh token returned by
refresh_access_token() every single time, not just the new access
token — this is a real, documented Intuit behavior, not an edge case,
and getting it wrong silently breaks the whole connection days later
when the old, no-longer-valid refresh token is used again.

⚠️ NOT LIVE-TESTED: no Intuit developer app has been registered and no
live OAuth flow has been completed from this environment — built
directly from Intuit's current published API reference, not guessed,
but genuinely needs a real smoke test (ideally against Intuit's free
sandbox company first) before being trusted for a real company's books.
Same honest caveat this codebase already applies to Twilio, RentCast,
and Seam.
"""
import os
import asyncio

import httpx

QUICKBOOKS_CLIENT_ID = os.getenv("QUICKBOOKS_CLIENT_ID")
QUICKBOOKS_CLIENT_SECRET = os.getenv("QUICKBOOKS_CLIENT_SECRET")
QUICKBOOKS_REDIRECT_URI = os.getenv("QUICKBOOKS_REDIRECT_URI")
QUICKBOOKS_SANDBOX = os.getenv("QUICKBOOKS_SANDBOX", "false").lower() == "true"

AUTHORIZATION_BASE_URL = "https://appcenter.intuit.com/connect/oauth2"
TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
API_BASE_URL = "https://sandbox-quickbooks.api.intuit.com" if QUICKBOOKS_SANDBOX else "https://quickbooks.api.intuit.com"
MINOR_VERSION = "75"  # current as of Aug 2025 — Intuit deprecated 1-74; always send the latest


class QuickBooksNotConfigured(Exception):
    pass


class QuickBooksApiError(Exception):
    pass


def _require_app_credentials():
    if not QUICKBOOKS_CLIENT_ID or not QUICKBOOKS_CLIENT_SECRET or not QUICKBOOKS_REDIRECT_URI:
        raise QuickBooksNotConfigured(
            "QUICKBOOKS_CLIENT_ID, QUICKBOOKS_CLIENT_SECRET, and QUICKBOOKS_REDIRECT_URI "
            "must all be set — register a free app at developer.intuit.com first."
        )


def get_authorization_url(state: str) -> str:
    """Step 1 of the real OAuth2 Authorization Code flow — the URL a
    staff member is sent to, where they log into their own real
    QuickBooks account and approve access. state is a real per-attempt
    CSRF token (routers/accounting.py generates and verifies it), not
    decorative — without it, a forged callback request could complete
    a connection on someone else's behalf."""
    _require_app_credentials()
    params = (
        f"client_id={QUICKBOOKS_CLIENT_ID}"
        f"&scope=com.intuit.quickbooks.accounting"
        f"&redirect_uri={QUICKBOOKS_REDIRECT_URI}"
        f"&response_type=code"
        f"&state={state}"
    )
    return f"{AUTHORIZATION_BASE_URL}?{params}"


def exchange_code_for_tokens(authorization_code: str) -> dict:
    """Step 3 of the flow — trades the real authorization code Intuit
    just redirected back with for an actual access + refresh token
    pair. Returns Intuit's real response shape: access_token,
    refresh_token, expires_in (seconds, always 3600), plus whatever
    realmId the caller already captured from the callback's own query
    string (Intuit doesn't include it in this response body)."""
    _require_app_credentials()
    try:
        response = httpx.post(
            TOKEN_URL,
            auth=(QUICKBOOKS_CLIENT_ID, QUICKBOOKS_CLIENT_SECRET),
            headers={"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "authorization_code",
                "code": authorization_code,
                "redirect_uri": QUICKBOOKS_REDIRECT_URI,
            },
            timeout=15.0,
        )
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as exc:
        raise QuickBooksApiError(f"Token exchange failed ({exc.response.status_code}): {exc.response.text[:300]}") from exc
    except httpx.RequestError as exc:
        raise QuickBooksApiError(f"Token exchange request failed: {exc}") from exc


def refresh_access_token(refresh_token: str) -> dict:
    """Refreshes an expired (or soon-to-expire) access token. CRITICAL,
    per this module's own docstring: the refresh_token in the RETURNED
    dict is a brand-new one, different from the one passed in — the
    caller must persist it immediately, or the next refresh attempt
    (using the now-stale old token) will fail and the whole connection
    will need to be manually reconnected."""
    _require_app_credentials()
    try:
        response = httpx.post(
            TOKEN_URL,
            auth=(QUICKBOOKS_CLIENT_ID, QUICKBOOKS_CLIENT_SECRET),
            headers={"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"},
            data={"grant_type": "refresh_token", "refresh_token": refresh_token},
            timeout=15.0,
        )
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as exc:
        raise QuickBooksApiError(f"Token refresh failed ({exc.response.status_code}): {exc.response.text[:300]}") from exc
    except httpx.RequestError as exc:
        raise QuickBooksApiError(f"Token refresh request failed: {exc}") from exc


def _api_request(method: str, access_token: str, realm_id: str, path: str, json_body: dict | None = None) -> dict:
    url = f"{API_BASE_URL}/v3/company/{realm_id}{path}"
    separator = "&" if "?" in url else "?"
    url = f"{url}{separator}minorversion={MINOR_VERSION}"
    try:
        response = httpx.request(
            method, url,
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json", "Content-Type": "application/json"},
            json=json_body, timeout=20.0,
        )
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as exc:
        # QuickBooks' real error shape: {"Fault": {"Error": [{"Message":..., "Detail":..., "code":...}]}}
        # Surface the real Intuit error text, not just the raw HTTP status.
        raise QuickBooksApiError(f"QuickBooks API returned {exc.response.status_code}: {exc.response.text[:400]}") from exc
    except httpx.RequestError as exc:
        raise QuickBooksApiError(f"QuickBooks API request failed: {exc}") from exc
    except ValueError as exc:
        raise QuickBooksApiError(f"QuickBooks API returned an unparseable response: {exc}") from exc


def find_or_create_customer(access_token: str, realm_id: str, display_name: str, email: str | None = None) -> str:
    """Returns the real QuickBooks Customer Id for this resident,
    creating one if none matches yet — a Payment can't be recorded
    without a real CustomerRef. Matches by exact DisplayName first
    (QuickBooks' own query language, real syntax confirmed against
    Intuit's docs), since that's the one field QuickBooks itself
    enforces uniqueness on."""
    safe_name = display_name.replace("'", "\\'")
    query = f"SELECT * FROM Customer WHERE DisplayName = '{safe_name}'"
    result = _api_request("GET", access_token, realm_id, f"/query?query={query}")
    existing = result.get("QueryResponse", {}).get("Customer", [])
    if existing:
        return existing[0]["Id"]

    customer_body = {"DisplayName": display_name}
    if email:
        customer_body["PrimaryEmailAddr"] = {"Address": email}
    created = _api_request("POST", access_token, realm_id, "/customer", customer_body)
    return created["Customer"]["Id"]


def record_payment(access_token: str, realm_id: str, customer_id: str, amount: float, memo: str = "") -> dict:
    """Records a real QuickBooks Payment against a customer — the
    actual entity type Intuit uses for "money received," distinct from
    an Invoice (a bill sent) or a Deposit (a bank-side record). This is
    the first, real sync operation built here: pushing a rent payment
    already recorded in this app's own ledger (payments_col) into the
    real books. Pushing expenses/bills (the other real half of a
    complete sync) is genuine, separate future work — not built here,
    and not silently implied to exist."""
    body = {
        "CustomerRef": {"value": customer_id},
        "TotalAmt": round(amount, 2),
    }
    if memo:
        body["PrivateNote"] = memo[:4000]  # QuickBooks' own real field length limit
    return _api_request("POST", access_token, realm_id, "/payment", body)


# Async wrappers — same thread-pool pattern as every other service
# module in this codebase, so blocking httpx calls don't stall the
# FastAPI event loop.

async def exchange_code_for_tokens_async(authorization_code: str) -> dict:
    return await asyncio.to_thread(exchange_code_for_tokens, authorization_code)


async def refresh_access_token_async(refresh_token: str) -> dict:
    return await asyncio.to_thread(refresh_access_token, refresh_token)


async def find_or_create_customer_async(access_token: str, realm_id: str, display_name: str, email: str | None = None) -> str:
    return await asyncio.to_thread(find_or_create_customer, access_token, realm_id, display_name, email)


async def record_payment_async(access_token: str, realm_id: str, customer_id: str, amount: float, memo: str = "") -> dict:
    return await asyncio.to_thread(record_payment, access_token, realm_id, customer_id, amount, memo)
