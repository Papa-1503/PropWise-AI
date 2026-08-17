"""
Public vacancy feed — unauthenticated, read-only JSON listing of all
currently vacant units across all properties. This is the building block
for listing syndication: point a service like Zillow Rental Manager,
Apartments.com, or a syndication aggregator at this URL as your feed
source. No actual push integration is wired in — signing up with a real
syndication partner and configuring their feed importer to pull from
this URL is a separate, manual step outside this codebase.
"""
from fastapi import APIRouter
from db import properties_col

router = APIRouter(prefix="/api/public", tags=["public"])


@router.get("/vacancies")
async def list_vacancies():
    cursor = properties_col.find({})
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
