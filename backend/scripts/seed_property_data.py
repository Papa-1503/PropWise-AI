"""
Seeds a realistic simulation dataset on top of seed_users.py: a property
with several units in different states, leases, maintenance tickets, AI
recommendations, and revenue history — so the Dashboard, Actions, and
Payments tabs show real numbers instead of zeros.

Run from the backend/ directory:
    python -m scripts.seed_property_data

Safe to re-run — skips anything that already exists by its natural key.
"""
import asyncio
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timezone, timedelta
from db import properties_col, leases_col, tickets_col, ai_actions_col, payments_col

PROPERTY_ID = "sunset-apartments"

UNITS = [
    {"unitId": "101", "status": "occupied", "rent": 1450, "bedrooms": 2, "bathrooms": 1},
    {"unitId": "102", "status": "occupied", "rent": 1395, "bedrooms": 1, "bathrooms": 1},
    {"unitId": "103", "status": "vacant", "rent": 1400, "bedrooms": 1, "bathrooms": 1},
    {"unitId": "104", "status": "occupied", "rent": 1600, "bedrooms": 2, "bathrooms": 2},
    {"unitId": "105", "status": "occupied", "rent": 1550, "bedrooms": 2, "bathrooms": 1},
    {"unitId": "106", "status": "maintenance_hold", "rent": 1400, "bedrooms": 1, "bathrooms": 1},
    {"unitId": "107", "status": "occupied", "rent": 1750, "bedrooms": 3, "bathrooms": 2},
    {"unitId": "108", "status": "vacant", "rent": 1425, "bedrooms": 1, "bathrooms": 1},
]

LEASES = [
    {"unitId": "101", "residentName": "John Smith", "residentEmail": "tenant@rentflow.demo", "rent": 1450, "months_in": 8, "months_left": 4, "renewalStatus": "not_sent"},
    {"unitId": "102", "residentName": "Maria Chen", "residentEmail": None, "rent": 1395, "months_in": 10, "months_left": 2, "renewalStatus": "sent"},
    {"unitId": "104", "residentName": "Devon Walker", "residentEmail": None, "rent": 1600, "months_in": 3, "months_left": 9, "renewalStatus": "not_sent"},
    {"unitId": "105", "residentName": "Priya Natarajan", "residentEmail": None, "rent": 1550, "months_in": 18, "months_left": 1, "renewalStatus": "sent"},
    {"unitId": "107", "residentName": "Sam Okoye", "residentEmail": None, "rent": 1750, "months_in": 5, "months_left": 7, "renewalStatus": "not_sent"},
]

TICKETS = [
    {"unitId": "101", "title": "Kitchen faucet dripping", "priority": "normal", "category": "plumbing", "status": "open"},
    {"unitId": "106", "title": "No heat — unit on maintenance hold", "priority": "urgent", "category": "hvac", "status": "in_progress"},
    {"unitId": "104", "title": "Bedroom outlet not working", "priority": "normal", "category": "electrical", "status": "open"},
    {"unitId": "107", "title": "Squeaky front door hinge", "priority": "normal", "category": "general", "status": "done"},
    {"unitId": "105", "title": "Garbage disposal jammed", "priority": "urgent", "category": "plumbing", "status": "open"},
]

AI_ACTIONS = [
    {
        "type": "renewal_campaign", "title": "Send renewal offer to Priya Natarajan (Unit 105)",
        "priority": "high", "rationale": "Lease ends in 30 days with no renewal sent yet; unit has an 18-month tenure and on-time payment history.",
        "projectedOutcome": "Avoids ~3 weeks of vacancy loss (~$1,550) if she leaves unprompted.",
        "estimatedValue": 1550, "affectedUnitIds": ["105"], "confidence": 82, "riskLevel": "low",
        "plannedSteps": ["Draft renewal offer at current market rent", "Send via email", "Follow up in 5 days if no response"],
    },
    {
        "type": "collections_reminder", "title": "Send payment reminder — Unit 101 rent overdue",
        "priority": "medium", "rationale": "This month's rent charge is unpaid and 5 days past due for an otherwise reliable tenant.",
        "projectedOutcome": "Most reminders at this stage resolve within 3-4 days without escalation.",
        "estimatedValue": 1450, "affectedUnitIds": ["101"], "confidence": 75, "riskLevel": "low",
        "plannedSteps": ["Send friendly payment reminder", "Escalate to formal notice if unpaid after 10 days"],
    },
    {
        "type": "rent_adjustment", "title": "Consider rent increase for Unit 107 at renewal",
        "priority": "low", "rationale": "Unit 107 is a 3BR currently below comparable units of the same size in the portfolio.",
        "projectedOutcome": "Estimated $50-75/mo upside if adjusted at next renewal.",
        "estimatedValue": 600, "affectedUnitIds": ["107"], "confidence": 61, "riskLevel": "medium",
        "plannedSteps": ["Pull comparable rents for similar 3BR units nearby", "Propose adjustment at next renewal offer"],
    },
]


async def seed():
    now = datetime.now(timezone.utc)

    existing_property = await properties_col.find_one({"_id": PROPERTY_ID})
    if existing_property:
        print(f"Skipping property {PROPERTY_ID} — already exists")
    else:
        await properties_col.insert_one({
            "_id": PROPERTY_ID,
            "name": "Sunset Apartments",
            "address": "4200 Sunset Ave, Minneapolis, MN",
            "units": UNITS,
            "createdAt": now,
        })
        print(f"Created property {PROPERTY_ID} with {len(UNITS)} units")

    for lease in LEASES:
        existing = await leases_col.find_one({"propertyId": PROPERTY_ID, "unitId": lease["unitId"]})
        if existing:
            print(f"Skipping lease for unit {lease['unitId']} — already exists")
            continue
        start = now - timedelta(days=lease["months_in"] * 30)
        end = now + timedelta(days=lease["months_left"] * 30)
        doc = {
            "propertyId": PROPERTY_ID, "unitId": lease["unitId"],
            "residentName": lease["residentName"], "residentEmail": lease["residentEmail"],
            "startDate": start, "endDate": end, "rent": lease["rent"],
            "renewalStatus": lease["renewalStatus"], "balance": 0,
            "createdAt": now,
        }
        await leases_col.insert_one(doc)
        print(f"Created lease: Unit {lease['unitId']} — {lease['residentName']}")

   
