"""
Smart lock access via Seam (getseam.co) — a real, unified API covering
many lock brands (August, Schlage, Yale, Kwikset, SmartRent, and more)
through one integration, the same "unified layer over many providers"
reasoning already applied to market_rent_service.py (RentCast over a
single MLS) — a property portfolio realistically has a mix of lock
hardware across buildings, and locking this app to one specific brand's
proprietary API would mean re-integrating every time a different
building uses different hardware.

Same architectural template as stripe_service.py/twilio: sync core
functions plus async wrappers, honest exceptions rather than a silent
no-op. Genuinely simpler than Stripe/QuickBooks here — Seam uses a
plain API key (Authorization: Bearer), not an OAuth flow, so this is
usable the moment a key is added, no separate connect/callback step
needed.

Required environment variable:
    SEAM_API_KEY   — from a Seam workspace (console.getseam.com);
                      real locks need to be physically installed and
                      connected to Seam's supported providers first —
                      this app only talks to devices already connected
                      there, it doesn't provision hardware.

SeamNotConfigured: SEAM_API_KEY isn't set.
SeamApiError: the API call itself failed or Seam reported a real error.

⚠️ NOT LIVE-TESTED: no network path to connect.getseam.com from this
build environment, and no live Seam workspace/devices exist to test
against — built directly from Seam's own published API reference
(confirmed real endpoint paths, auth header, and response shapes), not
guessed. Same honest caveat this codebase already applies to Twilio
Voice/SMS and RentCast — needs a real smoke test against an actual
connected lock before being trusted for the first live use.
"""
import os
import asyncio

import httpx

SEAM_API_KEY = os.getenv("SEAM_API_KEY")
SEAM_BASE_URL = "https://connect.getseam.com"


class SeamNotConfigured(Exception):
    pass


class SeamApiError(Exception):
    pass


def _request(method: str, path: str, json_body: dict | None = None) -> dict:
    if not SEAM_API_KEY:
        raise SeamNotConfigured("SEAM_API_KEY is not set in the environment.")
    try:
        response = httpx.request(
            method, f"{SEAM_BASE_URL}{path}",
            headers={"Authorization": f"Bearer {SEAM_API_KEY}", "Accept": "application/json"},
            json=json_body, timeout=15.0,
        )
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as exc:
        raise SeamApiError(f"Seam API returned {exc.response.status_code}: {exc.response.text[:300]}") from exc
    except httpx.RequestError as exc:
        raise SeamApiError(f"Seam API request failed: {exc}") from exc
    except ValueError as exc:
        raise SeamApiError(f"Seam API returned an unparseable response: {exc}") from exc


def list_devices() -> list[dict]:
    """Every lock device currently connected to this Seam workspace —
    staff match these against real units via unit.seamDeviceId (see
    models.py's UnitIn) once devices are actually connected."""
    data = _request("GET", "/devices/list")
    return data.get("devices", [])


def lock_door(device_id: str) -> dict:
    return _request("POST", "/locks/lock", {"device_id": device_id})


def unlock_door(device_id: str) -> dict:
    return _request("POST", "/locks/unlock", {"device_id": device_id})


def create_access_code(
    device_id: str,
    name: str,
    code: str | None = None,
    starts_at: str | None = None,
    ends_at: str | None = None,
) -> dict:
    """Creates a real, time-bounded PIN code on the physical lock — the
    genuinely valuable operation for this app: a vendor dispatched to a
    ticket, or a prospect with a booked self-guided tour slot, gets a
    real code that only works during their actual appointment window,
    not a shared master code or a physical key that needs tracking
    down afterward. code is optional — omit it to let Seam generate a
    random one (the safer default; a staff-chosen code risks
    collisions/predictability Seam's own generation avoids)."""
    body = {"device_id": device_id, "name": name}
    if code:
        body["code"] = code
    if starts_at:
        body["starts_at"] = starts_at
    if ends_at:
        body["ends_at"] = ends_at
    return _request("POST", "/access_codes/create", body)


def delete_access_code(access_code_id: str) -> dict:
    return _request("POST", "/access_codes/delete", {"access_code_id": access_code_id})


# Async wrappers — run the blocking httpx calls in a thread pool so
# they don't stall the FastAPI event loop, same pattern as
# sms_service.send_sms_async / market_rent_service.fetch_comps_async.

async def list_devices_async() -> list[dict]:
    return await asyncio.to_thread(list_devices)


async def lock_door_async(device_id: str) -> dict:
    return await asyncio.to_thread(lock_door, device_id)


async def unlock_door_async(device_id: str) -> dict:
    return await asyncio.to_thread(unlock_door, device_id)


async def create_access_code_async(
    device_id: str, name: str, code: str | None = None,
    starts_at: str | None = None, ends_at: str | None = None,
) -> dict:
    return await asyncio.to_thread(create_access_code, device_id, name, code, starts_at, ends_at)


async def delete_access_code_async(access_code_id: str) -> dict:
    return await asyncio.to_thread(delete_access_code, access_code_id)
