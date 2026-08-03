"""
One-off seed script: creates a staff account and a tenant account so you
can log in and test the app immediately, without going through the
register endpoint by hand.

Run from the backend/ directory (so the relative imports resolve):
    python -m scripts.seed_users

Safe to re-run — it skips any account whose email already exists.
"""
import asyncio
import sys
import os

# allow running as `python -m scripts.seed_users` from backend/
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timezone, timedelta
from db import users_col, vendors_col, payments_col
from auth import hash_password

SEED_ACCOUNTS = [
    {
        "email": "staff@rentflow.demo",
        "password": "demo1234",
        "name": "D. Okafor",
        "role": "staff",
        "propertyId": None,
        "unitId": None,
    },
    {
        "email": "tenant@rentflow.demo",
        "password": "demo1234",
        "name": "John Smith",
        "role": "tenant",
        "propertyId": "sunset-apartments",
        "unitId": "101",
    },
]


SEED_VENDORS = [
    {"name": "Metro Plumbing", "category": "plumbing", "rating": 4.7, "distanceMiles": 3.2, "avgArrivalHours": 2, "baseCost": 240, "active": True},
    {"name": "Ace Electric Co.", "category": "electrical", "rating": 4.5, "distanceMiles": 5.8, "avgArrivalHours": 4, "baseCost": 180, "active": True},
    {"name": "CoolFlow HVAC", "category": "hvac", "rating": 4.8, "distanceMiles": 6.1, "avgArrivalHours": 6, "baseCost": 320, "active": True},
    {"name": "Handy General Repair", "category": "general", "rating": 4.2, "distanceMiles": 2.1, "avgArrivalHours": 3, "baseCost": 120, "active": True},
]


async def seed():
    for account in SEED_ACCOUNTS:
        existing = await users_col.find_one({"email": account["email"]})
        if existing:
            print(f"Skipping {account['email']} — already exists")
            continue

        doc = {**account}
        doc["password"] = hash_password(doc.pop("password"))
        doc["createdAt"] = datetime.now(timezone.utc)
        await users_col.insert_one(doc)
        print(f"Created {account['role']} account: {account['email']} / demo1234")

    for vendor in SEED_VENDORS:
        existing = await vendors_col.find_one({"name": vendor["name"]})
        if existing:
            print(f"Skipping vendor {vendor['name']} — already exists")
            continue
        doc = {**vendor, "createdAt": datetime.now(timezone.utc)}
        await vendors_col.insert_one(doc)
        print(f"Created vendor: {vendor['name']} ({vendor['category']})")

    # A couple of sample rent charges for the seeded tenant unit, so the
    # Payments tab and CollectionsAI stats have something real to show —
    # one overdue (to demo the delinquent view), one paid.
    sample_charges = [
        {
            "propertyId": "sunset-apartments", "unitId": "101",
            "amountDue": 1450.0, "dueDate": datetime.now(timezone.utc) - timedelta(days=10),
            "description": "Monthly rent — last month", "amountPaid": 1450.0,
            "paidDate": datetime.now(timezone.utc) - timedelta(days=9),
        },
        {
            "propertyId": "sunset-apartments", "unitId": "101",
            "amountDue": 1450.0, "dueDate": datetime.now(timezone.utc) - timedelta(days=5),
            "description": "Monthly rent — this month", "amountPaid": 0.0, "paidDate": None,
        },
    ]
    for charge in sample_charges:
        existing = await payments_col.find_one({
            "propertyId": charge["propertyId"], "unitId": charge["unitId"], "dueDate": charge["dueDate"]
        })
        if existing:
            continue
        doc = {**charge, "createdAt": datetime.now(timezone.utc)}
        await payments_col.insert_one(doc)
        print(f"Created sample charge: Unit {charge['unitId']} — ${charge['amountDue']}")

    print("\nDone. Log in with:")
    print("  staff@rentflow.demo   / demo1234  (staff console)")
    print("  tenant@rentflow.demo  / demo1234  (resident portal)")


if __name__ == "__main__":
    asyncio.run(seed())
