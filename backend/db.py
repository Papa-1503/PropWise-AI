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
unit_baseline_photos_col = db["unit_baseline_photos"]
condition_reports_col = db["condition_reports"]
tickets_col = db["maintenance_tickets"]
properties_col = db["properties"]
leases_col = db["leases"]
users_col = db["users"]
ai_actions_col = db["ai_actions"]
vendors_col = db["vendors"]
vendor_bids_col = db["vendor_bids"]
payments_col = db["payments"]
notifications_col = db["notifications"]
push_subscriptions_col = db["push_subscriptions"]
market_rent_analyses_col = db["market_rent_analyses"]
posts_col = db["posts"]
leads_col = db["leads"]
documents_col = db["documents"]
gallery_photos_col = db["gallery_photos"]
screening_col = db["screening_requests"]
bank_lines_col = db["bank_statement_lines"]
dashboard_prefs_col = db["dashboard_preferences"]
workflows_col = db["workflows"]
workflow_runs_col = db["workflow_runs"]
maintenance_schedules_col = db["maintenance_schedules"]
communications_col = db["communications"]
on_call_shifts_col = db["on_call_shifts"]
on_call_log_col = db["on_call_log"]
audit_log_col = db["audit_log"]
budgets_col = db["budgets"]
kb_articles_col = db["kb_articles"]
supplies_col = db["supplies"]
supply_orders_col = db["supply_orders"]
repair_items_col = db["repair_items"]
labor_rates_col = db["labor_rates"]
fixed_assets_col = db["fixed_assets"]
capital_projects_col = db["capital_projects"]
custom_field_definitions_col = db["custom_field_definitions"]
custom_field_values_col = db["custom_field_values"]
communication_templates_col = db["communication_templates"]
custom_roles_col = db["custom_roles"]
custom_views_col = db["custom_views"]
custom_reports_col = db["custom_reports"]
application_questions_col = db["application_questions"]
packages_col = db["packages"]
community_posts_col = db["community_posts"]
late_notices_col = db["late_notices"]
async def ensure_indexes():
    """Call once at app startup (see main.py) to keep queries fast."""
    await inspections_col.create_index([("propertyId", 1), ("unitId", 1)])
    await tickets_col.create_index([("propertyId", 1), ("status", 1)])
    await tickets_col.create_index([("sourceInspectionId", 1)])
    await leases_col.create_index([("propertyId", 1), ("endDate", 1)])
    await push_subscriptions_col.create_index([("userId", 1), ("endpoint", 1)], unique=True)
    await users_col.create_index("email", unique=True)
    await ai_actions_col.create_index([("propertyId", 1), ("status", 1)])
    await vendors_col.create_index("category")
    await vendors_col.create_index("insuranceExpiresDate", sparse=True)
    await vendors_col.create_index("licenseExpiresDate", sparse=True)
    await vendor_bids_col.create_index("ticketId")
    await unit_baseline_photos_col.create_index([("propertyId", 1), ("unitId", 1), ("room", 1)])
    await condition_reports_col.create_index([("propertyId", 1), ("unitId", 1), ("createdAt", -1)])
    await payments_col.create_index([("propertyId", 1), ("unitId", 1), ("dueDate", 1)])
    await payments_col.create_index("status")
    await notifications_col.create_index([("userId", 1), ("read", 1), ("createdAt", -1)])
    await posts_col.create_index([("createdAt", -1)])
    await workflows_col.create_index([("status", 1)])
    await workflow_runs_col.create_index([("workflowId", 1), ("startedAt", -1)])
    await maintenance_schedules_col.create_index([("propertyId", 1), ("nextDueDate", 1)])
    await communications_col.create_index([("propertyId", 1), ("unitId", 1), ("createdAt", -1)])
    # Two indexes for on-call: one for "who's on call right now" (the
    # hot-path query — filter by propertyId, find the shift whose
    # window contains now), one for the plain shift-list/calendar view
    # sorted chronologically.
    await on_call_shifts_col.create_index([("propertyIds", 1), ("startTime", 1), ("endTime", 1)])
    await on_call_shifts_col.create_index([("startTime", 1)])
    await on_call_log_col.create_index([("recordingSid", 1)], unique=True, sparse=True)
    await on_call_log_col.create_index([("createdAt", -1)])
    # Two indexes for audit log: the common "show me everything on this
    # record" lookup, and the common "show me everything this person
    # did" lookup. Both sorted newest-first since that's how an audit
    # log is actually read.
    await audit_log_col.create_index([("targetType", 1), ("targetId", 1), ("createdAt", -1)])
    await audit_log_col.create_index([("actorId", 1), ("createdAt", -1)])
    # One budget per property+category+period - the natural unique key
    # for "what did this property expect to spend on this category this
    # month", preventing an accidental duplicate budget line for the
    # same real thing.
    await budgets_col.create_index([("propertyId", 1), ("category", 1), ("period", 1)], unique=True)
    await bank_lines_col.create_index([("propertyId", 1), ("category", 1), ("date", 1)])
    await kb_articles_col.create_index([("category", 1), ("updatedAt", -1)])
    # propertyId, not global - supplies are tracked per property, same
    # as everything else in this app
    await supplies_col.create_index([("propertyId", 1), ("category", 1)])
    await supply_orders_col.create_index([("propertyId", 1), ("createdAt", -1)])
    await repair_items_col.create_index([("damageType", 1)])
    await labor_rates_col.create_index([("category", 1)], unique=True)
    await fixed_assets_col.create_index([("propertyId", 1)])
    await capital_projects_col.create_index([("propertyId", 1), ("targetDate", 1)])
    await custom_field_definitions_col.create_index([("entityType", 1), ("fieldName", 1)], unique=True)
    await custom_field_values_col.create_index([("entityType", 1), ("entityId", 1), ("fieldName", 1)], unique=True)
    await community_posts_col.create_index([("propertyId", 1), ("createdAt", -1)])
    await late_notices_col.create_index([("propertyId", 1), ("unitId", 1), ("createdAt", -1)])
    await custom_views_col.create_index([("ownerId", 1), ("entityType", 1)])
    await packages_col.create_index([("propertyId", 1), ("pickedUp", 1), ("loggedAt", -1)])
    await market_rent_analyses_col.create_index([("propertyId", 1), ("unitId", 1), ("createdAt", -1)])
