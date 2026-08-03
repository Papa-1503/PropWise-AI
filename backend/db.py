"""
Motor (async MongoDB) client setup.

Adjust MONGO_URL / DB_NAME to match your actual deployment — these
default to local dev values via environment variables.
"""
import os
from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "rentflow")

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

# Collections used across routers
inspections_col = db["inspections"]
photos_col = db["inspection_photos"]
tickets_col = db["maintenance_tickets"]
properties_col = db["properties"]
leases_col = db["leases"]
users_col = db["users"]
ai_actions_col = db["ai_actions"]
vendors_col = db["vendors"]
payments_col = db["payments"]
notifications_col = db["notifications"]
posts_col = db["posts"]


async def ensure_indexes():
    """Call once at app startup (see main.py) to keep queries fast."""
    await inspections_col.create_index([("propertyId", 1), ("unitId", 1)])
    await tickets_col.create_index([("propertyId", 1), ("status", 1)])
    await tickets_col.create_index([("sourceInspectionId", 1)])
    await leases_col.create_index([("propertyId", 1), ("endDate", 1)])
    await users_col.create_index("email", unique=True)
    await ai_actions_col.create_index([("propertyId", 1), ("status", 1)])
    await vendors_col.create_index("category")
    await payments_col.create_index([("propertyId", 1), ("unitId", 1), ("dueDate", 1)])
    await payments_col.create_index("status")
    await notifications_col.create_index([("userId", 1), ("read", 1), ("createdAt", -1)])
    await posts_col.create_index([("createdAt", -1)])
