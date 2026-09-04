"""
Portfolio "what-if" scenario simulation — real arithmetic over the live
rent roll, never LLM-guessed numbers. Confirmed genuinely missing
earlier in this project's history (flagged as real, new work, distinct
from anything already built): nothing anywhere computed the effect of
a hypothetical rent change or occupancy shift.

Same honesty pattern already established elsewhere in this app
(dashboard.py's health score, vendors.py's recommended_vendors,
renewal_risk_service.py): every number here is plain, deterministic
Python arithmetic over real Mongo data. These functions are called as
tools by routers/scenario_ai.py's Claude tool-use loop — the AI's job
is deciding WHICH function to call and how to narrate the result, it
never computes a dollar figure itself. This mirrors market_rent.py's
"AI reasoning grounded only in computed statistics" principle,
extended from market pricing to internal what-if planning.

Deliberately scoped to real, currently-known data (rent roll,
occupancy, delinquency) rather than promising true predictive
modeling (renewal probability under a rent increase, elasticity of
demand for a re-listed vacant unit) — this app doesn't have a
historical dataset to validate a prediction like that against yet
(the same honest limitation renewal_risk_service.py's own docstring
already states). These are "what does this change do to my numbers
today," not "what will residents actually do."
"""
from datetime import datetime, timezone

from db import properties_col, payments_col


async def _get_units(property_ids: list[str] | None) -> list[dict]:
    """Every real unit in scope, each tagged with its own propertyId/
    propertyName so results can report both portfolio totals and a
    per-property breakdown."""
    query = {"_id": {"$in": property_ids}} if property_ids else {}
    props = await properties_col.find(query).to_list(length=500)
    units = []
    for p in props:
        for u in p.get("units", []):
            units.append({**u, "propertyId": str(p["_id"]), "propertyName": p.get("name", "")})
    return units


async def _delinquent_balance(property_ids: list[str] | None) -> float:
    query: dict = {"dueDate": {"$lt": datetime.now(timezone.utc)}}
    if property_ids:
        query["propertyId"] = {"$in": property_ids}
    charges = await payments_col.find(query).to_list(length=2000)
    return round(sum(
        c["amountDue"] - c.get("amountPaid", 0)
        for c in charges
        if c.get("amountPaid", 0) < c.get("amountDue", 0)
    ), 2)


async def portfolio_snapshot(property_ids: list[str] | None = None) -> dict:
    """Real current-state baseline: occupancy, rent roll, delinquency -
    for the AI to answer plain "what's my current state" questions, or
    as the "before" side of a what-if without a separate call."""
    units = await _get_units(property_ids)
    occupied = [u for u in units if u.get("status") == "occupied"]
    vacant = [u for u in units if u.get("status") == "vacant"]
    hold = [u for u in units if u.get("status") == "maintenance_hold"]

    monthly_rent_roll = round(sum(u.get("rent", 0) for u in occupied), 2)
    avg_rent = round(monthly_rent_roll / len(occupied), 2) if occupied else 0

    return {
        "totalUnits": len(units),
        "occupiedUnits": len(occupied),
        "vacantUnits": len(vacant),
        "maintenanceHoldUnits": len(hold),
        "occupancyPct": round(len(occupied) / len(units) * 100, 1) if units else 0,
        "currentMonthlyRentRoll": monthly_rent_roll,
        "averageOccupiedRent": avg_rent,
        "currentDelinquentBalance": await _delinquent_balance(property_ids),
    }


async def simulate_rent_increase(property_ids: list[str] | None, percent: float) -> dict:
    """Real per-unit math: new_rent = current_rent * (1 + percent/100)
    for every currently OCCUPIED unit in scope. Vacant units are
    reported separately, not included in the rent-roll delta — raising
    the asking rent on an empty unit doesn't change today's rent roll
    the way raising an occupied unit's rent does; it only affects
    future listing price, a different, separate decision."""
    units = await _get_units(property_ids)
    occupied = [u for u in units if u.get("status") == "occupied"]
    vacant_count = sum(1 for u in units if u.get("status") == "vacant")

    current_total = round(sum(u.get("rent", 0) for u in occupied), 2)
    new_total = round(sum(u.get("rent", 0) * (1 + percent / 100) for u in occupied), 2)
    dollar_increase = round(new_total - current_total, 2)

    # A handful of real example units so the AI can cite specifics, not
    # just the aggregate - capped rather than listing every unit in a
    # 1000+ unit portfolio.
    examples = [
        {
            "propertyName": u["propertyName"], "unitId": u.get("unitId"),
            "currentRent": u.get("rent", 0),
            "newRent": round(u.get("rent", 0) * (1 + percent / 100), 2),
        }
        for u in occupied[:8]
    ]

    return {
        "percentIncrease": percent,
        "occupiedUnitsAffected": len(occupied),
        "vacantUnitsNotAffected": vacant_count,
        "currentMonthlyRentRoll": current_total,
        "newMonthlyRentRoll": new_total,
        "monthlyDollarIncrease": dollar_increase,
        "annualDollarIncrease": round(dollar_increase * 12, 2),
        "exampleUnits": examples,
    }


async def simulate_occupancy_change(property_ids: list[str] | None, unit_delta: int) -> dict:
    """Real revenue impact of unit_delta more (positive) or fewer
    (negative) occupied units, at the scope's real current average
    occupied rent - e.g. unit_delta=-3 answers "what if 3 more units
    go vacant," unit_delta=2 answers "what if I fill 2 more vacancies."
    Uses the average of CURRENTLY occupied units' real rent as the
    per-unit estimate, since that's the only real rent data available
    for a unit that isn't occupied yet (a vacant unit's own listed
    rent, if any, may be stale or not yet set - the average of what's
    actually being collected today is the more honest estimate)."""
    units = await _get_units(property_ids)
    occupied = [u for u in units if u.get("status") == "occupied"]
    vacant_count = sum(1 for u in units if u.get("status") == "vacant")

    current_total = round(sum(u.get("rent", 0) for u in occupied), 2)
    avg_rent = round(current_total / len(occupied), 2) if occupied else 0
    monthly_impact = round(avg_rent * unit_delta, 2)

    if unit_delta < 0 and abs(unit_delta) > vacant_count + len(occupied):
        note = "This would mean more units going vacant than the portfolio actually has occupied — treat this as an extreme/illustrative scenario, not a realistic one."
    elif unit_delta > 0 and unit_delta > vacant_count:
        note = f"Only {vacant_count} units are actually vacant right now — filling more than that isn't possible without new units being added to the portfolio."
    else:
        note = None

    return {
        "unitDelta": unit_delta,
        "currentOccupiedUnits": len(occupied),
        "currentVacantUnits": vacant_count,
        "averageOccupiedRentUsedForEstimate": avg_rent,
        "estimatedMonthlyRevenueImpact": monthly_impact,
        "estimatedAnnualRevenueImpact": round(monthly_impact * 12, 2),
        "note": note,
    }
