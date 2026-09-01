"""
Market rent comps — pulls comparable rental listings near a unit and
computes real pricing statistics from them.

Same architectural template as stripe_service.py/sms_service.py: sync
core function plus an async wrapper, honest exceptions rather than a
silent no-op or fabricated numbers.

Required environment variable:
    RENTCAST_API_KEY   — from rentcast.io (has a free tier: 50 requests/
                          month at time of writing). Chosen over a
                          general web-scrape approach because rent comps
                          need structured, verifiable data (exact
                          address, bed/bath/sqft match, distance) that a
                          scrape can't reliably guarantee — the same
                          reasoning this codebase already applies
                          elsewhere (Stripe over building a payment
                          processor, Twilio over building telephony).

MarketRentNotConfigured: RENTCAST_API_KEY isn't set.
MarketRentApiError: the API call itself failed or returned unusable data.

⚠️ NOT LIVE-TESTED: this environment has no network path to
api.rentcast.io, so the actual HTTP call and RentCast's real response
shape have never been exercised here — only reasoned from RentCast's
public API documentation. Treat the request/response handling below as
needing a live smoke test before relying on it, the same honest caveat
this codebase already applies to Twilio Voice/SMS elsewhere.
"""
import os
import asyncio

import httpx

RENTCAST_API_KEY = os.getenv("RENTCAST_API_KEY")
RENTCAST_BASE_URL = "https://api.rentcast.io/v1"


class MarketRentNotConfigured(Exception):
    pass


class MarketRentApiError(Exception):
    pass


def fetch_comps(
    address: str,
    bedrooms: float | None = None,
    bathrooms: float | None = None,
    square_footage: float | None = None,
) -> dict:
    """
    Returns RentCast's long-term-rent AVM response: a rent estimate plus
    a list of comparable listings, each with its own address, rent,
    bed/bath/sqft, and distance from the subject property. Raises
    MarketRentNotConfigured or MarketRentApiError rather than returning
    a fabricated or partial result — a pricing recommendation is only as
    trustworthy as the comps it's built from.
    """
    if not RENTCAST_API_KEY:
        raise MarketRentNotConfigured("RENTCAST_API_KEY is not set in the environment.")

    params = {"address": address, "propertyType": "Apartment"}
    if bedrooms is not None:
        params["bedrooms"] = bedrooms
    if bathrooms is not None:
        params["bathrooms"] = bathrooms
    if square_footage is not None:
        params["squareFootage"] = square_footage

    try:
        response = httpx.get(
            f"{RENTCAST_BASE_URL}/avm/rent/long-term",
            params=params,
            headers={"X-Api-Key": RENTCAST_API_KEY, "Accept": "application/json"},
            timeout=15.0,
        )
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPStatusError as exc:
        raise MarketRentApiError(f"RentCast API returned {exc.response.status_code}: {exc.response.text[:200]}") from exc
    except httpx.RequestError as exc:
        raise MarketRentApiError(f"RentCast API request failed: {exc}") from exc
    except ValueError as exc:  # JSON decode failure
        raise MarketRentApiError(f"RentCast API returned an unparseable response: {exc}") from exc

    comparables = data.get("comparables", [])
    if not comparables:
        raise MarketRentApiError("RentCast API returned zero comparable listings for this address.")

    return data


async def fetch_comps_async(
    address: str,
    bedrooms: float | None = None,
    bathrooms: float | None = None,
    square_footage: float | None = None,
) -> dict:
    """Async-safe wrapper — runs the blocking httpx call in a thread pool
    so it doesn't stall the FastAPI event loop, same pattern as
    sms_service.send_sms_async."""
    return await asyncio.to_thread(fetch_comps, address, bedrooms, bathrooms, square_footage)
