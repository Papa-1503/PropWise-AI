"""
Scale test seed script: generates 12 additional properties (13 total
with Sunset Apartments) at realistic portfolio scale — ~1,838 new units,
leases, payment history, maintenance tickets, a rotating tech pool, and
owner accounts. Used to confirm the multi-property data model holds up
under real volume before building more features on top of it.

Run from the backend/ directory:
    python -m scripts.seed_scale_test

Safe to re-run — skips any property that already exists by its _id.
Uses bulk inserts per collection rather than one-at-a-time, since this
generates thousands of documents.
"""
import asyncio
import math
import random
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timezone, timedelta
from db import properties_col, leases_col, tickets_col, payments_col, users_col
from auth import hash_password

random.seed(42)  # deterministic — same data every run for a given empty DB

PROPERTIES = [
    {"id": "riverside-commons", "name": "Riverside Commons", "address": "1200 Riverside Ave, Minneapolis, MN", "units": 240, "tier": 1.15},
    {"id": "northgate-towers", "name": "Northgate Towers", "address": "3400 Hennepin Ave, Minneapolis, MN", "units": 235, "tier": 1.05},
    {"id": "lakeview-terrace", "name": "Lakeview Terrace", "address": "800 Lake St W, Minneapolis, MN", "units": 220, "tier": 1.20},
    {"id": "cedar-ridge", "name": "Cedar Ridge Apartments", "address": "2100 Cedar Ave S, Minneapolis, MN", "units": 218, "tier": 0.95},
    {"id": "birchwood-flats", "name": "Birchwood Flats", "address": "4500 Nicollet Ave, Minneapolis, MN", "units": 165, "tier": 1.00},
    {"id": "maple-grove-res", "name": "Maple Grove Residences", "address": "900 Franklin Ave, Minneapolis, MN", "units": 150, "tier": 0.90},
    {"id": "willow-creek", "name": "Willow Creek Apartments", "address": "1600 Chicago Ave, Minneapolis, MN", "units": 145, "tier": 0.92},
    {"id": "oakdale-court", "name": "Oakdale Court", "address": "2800 Bloomington Ave, Minneapolis, MN", "units": 120, "tier": 0.88},
    {"id": "pinehurst-apts", "name": "Pinehurst Apartments", "address": "1100 Portland Ave, Minneapolis, MN", "units": 100, "tier": 0.85},
    {"id": "elm-street-lofts", "name": "Elm Street Lofts", "address": "500 Washington Ave N, Minneapolis, MN", "units": 95, "tier": 1.30},
    {"id": "hawthorne-heights", "name": "Hawthorne Heights", "address": "3300 Park Ave, Minneapolis, MN", "units": 85, "tier": 0.90},
    {"id": "ironwood-apts", "name": "Ironwood Apartments", "address": "700 Central Ave NE, Minneapolis, MN", "units": 65, "tier": 0.87},
]

# Unit mix: (bedrooms, bathrooms, base_rent, weight)
UNIT_TYPES = [
    (0, 1.0, 950, 0.15),   # studio
    (1, 1.0, 1150, 0.35),  # 1BR
    (2, 1.0, 1400, 0.25),  # 2BR/1BA
    (2, 2.0, 1550, 0.15),  # 2BR/2BA
    (3, 2.0, 1850, 0.10),  # 3BR
]

FIRST_NAMES = ["James", "Maria", "David", "Sarah", "Michael", "Jennifer", "Robert", "Linda", "William", "Emily",
               "Carlos", "Aisha", "Wei", "Fatima", "Daniel", "Sofia", "Kevin", "Nadia", "Marcus", "Grace"]
LAST_NAMES = ["Johnson", "Garcia", "Smith", "Williams", "Brown", "Jones", "Miller", "Davis", "Anderson", "Taylor",
              "Nguyen", "Patel", "Kim", "Hassan", "Larsen", "Rossi", "Okafor", "Chen", "Murphy", "Olsen"]

TICKET_TITLES = [
    ("Kitchen faucet dripping", "plumbing", "normal"),
    ("No heat in unit", "hvac", "urgent"),
    ("Outlet not working", "electrical", "normal"),
    ("Squeaky door hinge", "general", "normal"),
    ("Garbage disposal jammed", "plumbing", "urgent"),
    ("AC not cooling", "hvac", "urgent"),
    ("Broken window latch", "general", "normal"),
    ("Toilet running constantly", "plumbing", "normal"),
]


def pick_unit_type():
    r = random.random()
    cum = 0
    for beds, baths, rent, weight in UNIT_TYPES:
        cum += weight
        if r <= cum:
            return beds, baths, rent
    return UNIT_TYPES[-1][:3]


def generate_units(count, tier):
    units = []
    floors = max(1, math.ceil(count / 20))
    units_per_floor = math.ceil(count / floors)
    for i in range(count):
        floor = i // units_per_floor + 1
        position = i % units_per_floor + 1
        unit_num = f"{floor}{str(position).zfill(2)}"
        beds, baths, base_rent = pick_unit_type()
        rent = round(base_rent * tier * random.uniform(0.95, 1.08), -1)
        roll = random.random()
        if roll < 0.87:
            status = "occupied"
        elif roll < 0.97:
            status = "vacant"
        else:
            status = "maintenance_hold"
        units.append({
            "unitId": unit_num,
            "status": status,
            "rent": rent,
            "bedrooms": beds,
            "bathrooms": baths,
            "readyToList": True,
        })
    return units


async def seed():
    now = datetime.now(timezone.utc)

    # --- Rotating tech pool (3-4 techs covering all 12 new properties) ---
    all_property_ids = [p["id"] for p in PROPERTIES]
    tech_defs = [
        {"email": "tech1@rentflow.demo", "name": "Marcus Reilly"},
        {"email": "tech2@rentflow.demo", "name": "Aisha Bello"},
        {"email": "tech3@rentflow.demo", "name": "Devon Park"},
        {"email": "tech4@rentflow.demo", "name": "Grace Lindqvist"},
    ]
    # Split the 12 properties across 4 techs, 3 each
    tech_ids = []
    for i, tech in enumerate(tech_defs):
        existing = await users_col.find_one({"email": tech["email"]})
        if existing:
            tech_ids.append(existing["_id"])
            print(f"Skipping tech {tech['email']} — already exists")
            continue
        assigned = all_property_ids[i * 3:(i + 1) * 3]
        doc = {
            "email": tech["email"],
            "password": hash_password("demo1234"),
            "name": tech["name"],
            "role": "staff",
            "propertyId": None,
            "unitId": None,
            "assignedProperties": assigned,
            "createdAt": now,
        }
        result = await users_col.insert_one(doc)
        tech_ids.append(result.inserted_id)
        print(f"Created tech: {tech['email']} — assigned {assigned}")

    # --- Owner accounts (2 owners splitting the new portfolio) ---
    owner_defs = [
        {"email": "owner1@rentflow.demo", "name": "Patricia Ellsworth"},
        {"email": "owner2@rentflow.demo", "name": "Samuel Whitfield"},
    ]
    owner_ids = []
    for owner in owner_defs:
        existing = await users_col.find_one({"email": owner["email"]})
        if existing:
            owner_ids.append(str(existing["_id"]))
            print(f"Skipping owner {owner['email']} — already exists")
            continue
        doc = {
            "email": owner["email"],
            "password": hash_password("demo1234"),
            "name": owner["name"],
            "role": "owner",
            "propertyId": None,
            "unitId": None,
            "createdAt": now,
        }
        result = await users_col.insert_one(doc)
        owner_ids.append(str(result.inserted_id))
        print(f"Created owner: {owner['email']}")

    # --- Properties, units, leases, payments, tickets ---
    for idx, prop in enumerate(PROPERTIES):
        existing = await properties_col.find_one({"_id": prop["id"]})
        if existing:
            print(f"Skipping property {prop['id']} — already exists")
            continue

        units = generate_units(prop["units"], prop["tier"])
        owner_id = owner_ids[idx % len(owner_ids)]

        await properties_col.insert_one({
            "_id": prop["id"],
            "name": prop["name"],
            "address": prop["address"],
            "units": units,
            "ownerId": owner_id,
            "createdAt": now,
        })
        print(f"Created property {prop['id']} with {len(units)} units")

        # Leases + payment history for occupied units
        lease_docs = []
        charge_docs = []
        for unit in units:
            if unit["status"] != "occupied":
                continue
            months_in = random.randint(1, 30)
            term_months = random.choice([6, 12, 12, 12, 24])
            start = now - timedelta(days=months_in * 30)
            end = start + timedelta(days=term_months * 30)
            resident_name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
            renewal_status = "not_sent"
            days_to_expiry = (end - now).days
            if 0 < days_to_expiry <= 45:
                renewal_status = random.choice(["not_sent", "sent"])

            lease_docs.append({
                "propertyId": prop["id"],
                "unitId": unit["unitId"],
                "residentName": resident_name,
                "residentEmail": None,
                "startDate": start,
                "endDate": end,
                "rent": unit["rent"],
                "renewalStatus": renewal_status,
                "balance": 0,
                "createdAt": now,
            })

            # 2-3 months of charge history, mostly on-time, some late
            for m in range(random.randint(2, 3)):
                due = now - timedelta(days=30 * m + random.randint(0, 5))
                on_time = random.random() < 0.85
                charge_docs.append({
                    "propertyId": prop["id"],
                    "unitId": unit["unitId"],
                    "amountDue": unit["rent"],
                    "dueDate": due,
                    "description": "Monthly rent",
                    "amountPaid": unit["rent"] if on_time else (0.0 if m == 0 else unit["rent"]),
                    "paidDate": (due + timedelta(days=1)) if on_time else (None if m == 0 else due + timedelta(days=8)),
                    "createdAt": now,
                })

        if lease_docs:
            await leases_col.insert_many(lease_docs)
        if charge_docs:
            await payments_col.insert_many(charge_docs)
        print(f"  {len(lease_docs)} leases, {len(charge_docs)} charges")

        # Maintenance tickets — ~8% of units get one, assigned to the
        # tech covering this property
        assigned_tech = await users_col.find_one({"role": "staff", "assignedProperties": prop["id"]})
        ticket_docs = []
        for unit in units:
            if random.random() < 0.08:
                title, category, priority = random.choice(TICKET_TITLES)
                status = random.choice(["open", "open", "in_progress", "done"])
                ticket_docs.append({
                    "propertyId": prop["id"],
                    "unitId": unit["unitId"],
                    "title": title,
                    "priority": priority,
                    "source": "staff",
                    "sourceInspectionId": None,
                    "room": None,
                    "assignee": assigned_tech.get("email") if assigned_tech else None,
                    "category": category,
                    "status": status,
                    "createdAt": now,
                })
        if ticket_docs:
            await tickets_col.insert_many(ticket_docs)
        print(f"  {len(ticket_docs)} maintenance tickets")

    print("\nScale test data seeded. 12 new properties, ~1,838 new units.")


if __name__ == "__main__":
    asyncio.run(seed())
