"""
Cross-building pricing comparison - "Building 5 is 12% below what the
rest of your portfolio charges for comparable units."

Deliberately NOT built on top of market_rent.py's external RentCast
comps - that feature answers a different question ("what does the
broader local market charge"), needs a real address + a working
external API call per unit, and is explicitly noted in its own module
docstring as untested in this environment (no network path to
api.rentcast.io here). This feature answers a narrower, fully internal
question instead - "how does each of MY buildings compare to my OTHER
buildings for the same size unit" - using only real rent/bedroom data
this app already has, with zero external dependency. Same "AI
reasoning grounded only in computed statistics" principle used
throughout this app, except here there isn't even an AI step: the
comparison itself is plain arithmetic, honest and fully reproducible
without any model call.

Units are grouped by bedroom count (studio/1BR/2BR/etc.) rather than
compared unit-for-unit, since a studio and a 3-bedroom aren't
comparable regardless of which building they're in - bedroom count is
the one dimension already stored on every unit that makes a real,
like-for-like comparison possible without needing square footage or
other data this app doesn't currently track.

Only units with a real rent value set (rent > 0) are counted - a unit
with no rent on file yet contributes nothing rather than distorting an
average with a false zero.
"""
from collections import defaultdict

from db import properties_col

MIN_PCT_DIFF_TO_FLAG = 5.0  # below this, treat as noise, not a real gap


async def compare_pricing_across_buildings(org_id: str) -> list[dict]:
    """Real average rent per bedroom-count bucket, per building, each
    compared against the average of every OTHER building with at least
    one unit of that same bedroom count - never against itself, and
    never against a bucket with no real comparison data available.
    org_id is required and scopes which buildings are even considered -
    this was a real, live cross-tenant gap before this pass: any staff
    member of any organization could see every other organization's
    pricing data, and a comparison could even mix buildings from
    different organizations together into the same "rest of the
    portfolio" average."""
    properties = await properties_col.find({"orgId": org_id}).to_list(length=500)

    # rents_by_property[propertyId][bedroomCount] = [rent, rent, ...]
    rents_by_property: dict[str, dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))
    property_names: dict[str, str] = {}

    for p in properties:
        property_id = str(p["_id"])
        property_names[property_id] = p.get("name", property_id)
        for u in p.get("units", []):
            rent = u.get("rent", 0)
            bedrooms = u.get("bedrooms")
            if rent and rent > 0 and bedrooms is not None:
                rents_by_property[property_id][bedrooms].append(rent)

    results = []
    for property_id, buckets in rents_by_property.items():
        for bedrooms, rents in buckets.items():
            property_avg = sum(rents) / len(rents)

            # Every OTHER property's rents for this same bedroom count
            other_rents = [
                r
                for other_id, other_buckets in rents_by_property.items()
                if other_id != property_id
                for r in other_buckets.get(bedrooms, [])
            ]
            if not other_rents:
                continue  # no real comparison data - never fabricate one

            rest_of_portfolio_avg = sum(other_rents) / len(other_rents)
            if rest_of_portfolio_avg == 0:
                continue

            pct_diff = round((property_avg - rest_of_portfolio_avg) / rest_of_portfolio_avg * 100, 1)

            results.append({
                "propertyId": property_id,
                "propertyName": property_names[property_id],
                "bedrooms": bedrooms,
                "unitCount": len(rents),
                "propertyAvgRent": round(property_avg, 2),
                "restOfPortfolioAvgRent": round(rest_of_portfolio_avg, 2),
                "restOfPortfolioUnitCount": len(other_rents),
                "pctDiff": pct_diff,
                "flagged": abs(pct_diff) >= MIN_PCT_DIFF_TO_FLAG,
            })

    # Biggest real gaps first - that's what makes this useful to scan,
    # rather than a flat, unordered dump of every bedroom bucket.
    results.sort(key=lambda r: abs(r["pctDiff"]), reverse=True)
    return results
