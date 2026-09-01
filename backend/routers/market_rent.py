"""
Market rent pricing tool.

    GET /api/market-rent/analysis?propertyId=&unitId=  -> pull real comps
        near the unit, compute mean/median/min/max, and get an AI
        recommendation GROUNDED ONLY in the real comp numbers below it —
        not an independent guess. Logs every analysis for pricing history.
    GET /api/market-rent/history?propertyId=&unitId=    -> past analyses

Was the single biggest confirmed gap in this codebase (checked against
every router — nothing pulled real comparable listings or computed
pricing statistics anywhere). Real comps come from market_rent_service.py
(RentCast API) — genuinely NOT live-tested (no network path to
api.rentcast.io from the build/test environment), same honest caveat
already applied elsewhere in this codebase to Twilio Voice/SMS.

Staff-only. Never touches resident/tenant identity — same fair-housing-
safe grounding pattern already used in routers/ai_actions.py.
"""
import statistics
import json
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends
from bson import ObjectId
from anthropic import AsyncAnthropic
import os

from db import properties_col, market_rent_analyses_col
from models import MarketRentComp
from auth import require_staff
from market_rent_service import fetch_comps_async, MarketRentNotConfigured, MarketRentApiError

router = APIRouter(prefix="/api/market-rent", tags=["market-rent"])

anthropic_client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
MODEL = "claude-sonnet-4-6"


def compute_statistics(rents: list[float]) -> dict:
    """Plain arithmetic on real comp rents — no AI involved in the
    numbers themselves, only in the reasoning sentence built on top of
    them. Kept as its own function so it's directly testable without a
    network call."""
    return {
        "meanRent": round(statistics.mean(rents), 2),
        "medianRent": round(statistics.median(rents), 2),
        "minRent": round(min(rents), 2),
        "maxRent": round(max(rents), 2),
    }


async def generate_recommendation_reasoning(stats: dict, current_rent: float | None, comp_count: int) -> tuple[float, str]:
    """AI reasoning is grounded ONLY in the computed statistics passed in
    — never given raw comp addresses/tenant data, never asked to invent
    numbers of its own. If the call fails, falls back to the median
    (an honest, defensible default) with a plain-language note rather
    than blocking the whole analysis."""
    prompt = (
        f"Comparable rentals near this unit: {comp_count} comps found. "
        f"Mean rent: ${stats['meanRent']:.2f}. Median: ${stats['medianRent']:.2f}. "
        f"Range: ${stats['minRent']:.2f}-${stats['maxRent']:.2f}. "
        f"Current rent: {'$' + format(current_rent, '.2f') if current_rent else 'not set (vacant or new listing)'}. "
        "Recommend a specific rent price and explain your reasoning in 2-3 sentences, "
        "grounded only in the numbers above. Respond with ONLY JSON: "
        '{"recommendedRent": number, "reasoning": "..."}'
    )
    try:
        response = await anthropic_client.messages.create(
            model=MODEL, max_tokens=250,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = "".join(b.text for b in response.content if getattr(b, "type", None) == "text")
        raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        parsed = json.loads(raw)
        recommended = float(parsed["recommendedRent"])
        reasoning = str(parsed["reasoning"])
        if recommended <= 0:
            raise ValueError("non-positive recommended rent")
        return recommended, reasoning
    except Exception:
        return stats["medianRent"], (
            f"AI reasoning unavailable — defaulted to the median of {comp_count} comps "
            f"(${stats['medianRent']:.2f}) as a defensible, non-fabricated fallback."
        )


@router.get("/analysis")
async def market_rent_analysis(propertyId: str, unitId: str, user: dict = Depends(require_staff)):
    if not ObjectId.is_valid(propertyId):
        raise HTTPException(status_code=400, detail="Invalid property ID")
    property_doc = await properties_col.find_one({"_id": ObjectId(propertyId)})
    if not property_doc:
        raise HTTPException(status_code=404, detail="Property not found")
    if not property_doc.get("address"):
        raise HTTPException(status_code=400, detail="Property has no address on file — comps require a real address.")

    unit = next((u for u in property_doc.get("units", []) if u.get("unitId") == unitId), None)
    if not unit:
        raise HTTPException(status_code=404, detail="Unit not found on this property")

    try:
        raw = await fetch_comps_async(
            address=property_doc["address"],
            bedrooms=unit.get("bedrooms"),
            bathrooms=unit.get("bathrooms"),
            square_footage=unit.get("squareFootage"),
        )
    except MarketRentNotConfigured:
        raise HTTPException(status_code=501, detail="Market rent pricing isn't configured yet — RENTCAST_API_KEY is not set.")
    except MarketRentApiError as exc:
        raise HTTPException(status_code=502, detail=f"Couldn't fetch comps: {exc}")

    comparables = raw.get("comparables", [])
    comps = [
        MarketRentComp(
            address=c.get("formattedAddress"), rent=c["price"],
            bedrooms=c.get("bedrooms"), bathrooms=c.get("bathrooms"),
            squareFootage=c.get("squareFootage"), distanceMiles=c.get("distance"),
            correlation=c.get("correlation"),
        )
        for c in comparables if c.get("price")
    ]
    if len(comps) < 3:
        raise HTTPException(
            status_code=502,
            detail=f"Only {len(comps)} usable comps returned — too few to price confidently. Try again later or verify the property address.",
        )

    rents = [c.rent for c in comps]
    stats = compute_statistics(rents)
    current_rent = unit.get("rent") or None
    recommended_rent, reasoning = await generate_recommendation_reasoning(stats, current_rent, len(comps))

    doc = {
        "propertyId": propertyId, "unitId": unitId,
        "compCount": len(comps), **stats,
        "currentRent": current_rent, "recommendedRent": recommended_rent,
        "recommendationReasoning": reasoning,
        "comps": [c.model_dump() for c in comps],
        "createdAt": datetime.now(timezone.utc), "createdBy": user.get("email"),
    }
    result = await market_rent_analyses_col.insert_one(doc)
    doc["id"] = str(result.inserted_id)
    doc["createdAt"] = doc["createdAt"].isoformat()
    return doc


@router.get("/history")
async def market_rent_history(propertyId: str, unitId: str, user: dict = Depends(require_staff)):
    cursor = market_rent_analyses_col.find({"propertyId": propertyId, "unitId": unitId}).sort(
        [("createdAt", -1), ("_id", -1)]
    ).limit(50)
    analyses = await cursor.to_list(length=50)
    for a in analyses:
        a["id"] = str(a.pop("_id"))
        if isinstance(a.get("createdAt"), datetime):
            a["createdAt"] = a["createdAt"].isoformat()
    return {"analyses": analyses}
