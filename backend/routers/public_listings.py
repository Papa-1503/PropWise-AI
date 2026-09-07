"""
Public vacancy feed — unauthenticated, read-only JSON listing of all
currently vacant units across all properties. This is the building block
for listing syndication: point a service like Zillow Rental Manager,
Apartments.com, or a syndication aggregator at this URL as your feed
source. No actual push integration is wired in — signing up with a real
syndication partner and configuring their feed importer to pull from
this URL is a separate, manual step outside this codebase.

MULTI-TENANCY: this endpoint is public and unauthenticated, so there is
no user session to read an orgId from. A real, previously-live gap:
without an explicit orgId, this fed together every organization's
vacant units into one combined feed - a real cross-tenant data leak
(other landlords' vacancy/pricing data exposed to any public consumer,
with no way to even tell which listing belonged to which company).
orgId is now a REQUIRED query parameter - a real per-organization feed
URL (e.g. ?orgId=<their real org id>) is the correct long-term design
for a public syndication endpoint like this, matching how real
syndication feeds are typically issued per customer. Omitting it
returns an empty feed with an honest error, never a mixed-org dump.
"""
from fastapi import APIRouter, HTTPException
from db import properties_col

router = APIRouter(prefix="/api/public", tags=["public"])


@router.get("/vacancies")
async def list_vacancies(orgId: str):
    cursor = properties_col.find({"orgId": orgId})
    properties = await cursor.to_list(length=500)

    listings = []
    for p in properties:
        property_name = p.get("name", "")
        address = p.get("address", "")
        for unit in p.get("units", []):
            if unit.get("status") == "vacant":
                listings.append({
                    "propertyName": property_name,
                    "address": address,
                    "unitId": unit.get("unitId"),
                    "rent": unit.get("rent", 0),
                    "bedrooms": unit.get("bedrooms", 0),
                    "bathrooms": unit.get("bathrooms", 0),
                })

    return {"vacancies": listings, "count": len(listings)}
