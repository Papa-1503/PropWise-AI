"""
App entrypoint. If you already have a main.py, just copy the router
includes and the /uploads static mount into it — everything else here
(db, models, routers/*) drops into your existing project structure as-is.
"""
from dotenv import load_dotenv
load_dotenv()

import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from bson import ObjectId
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
import os
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

# Real error monitoring (Sentry) — genuinely missing before this. The
# email-config bug found and fixed earlier today (an invalid Mailgun
# API key silently breaking every outbound email for an unknown
# period) is exactly the class of problem this exists to catch
# automatically going forward, rather than only discovering it when a
# real customer notices something never arrived. SENTRY_DSN is
# optional - sentry_sdk.init() is a real, safe no-op with dsn=None
# (confirmed directly, not assumed), so this app runs completely
# normally, with no behavior change at all, until a real DSN is
# configured. traces_sample_rate is deliberately low (10%) - full
# request tracing on every request has a real, non-trivial overhead
# cost and quota cost that isn't justified for this app's real scale;
# 10% is enough to see real performance patterns without either.
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

sentry_sdk.init(
    dsn=os.getenv("SENTRY_DSN"),
    integrations=[StarletteIntegration(), FastApiIntegration()],
    traces_sample_rate=0.1,
    environment=os.getenv("SENTRY_ENVIRONMENT", "production"),
    release=os.getenv("RENDER_GIT_COMMIT"),
    # ^ Render sets this automatically to the real deployed commit SHA
    # - when present, Sentry can tell you exactly which deploy a given
    # error first appeared in, without this app needing its own
    # separate versioning scheme.
)

from db import ensure_indexes, users_col, properties_col, organizations_col, leases_col, tickets_col, vendors_col, payments_col, bank_lines_col, inspections_col, documents_col, leads_col, screening_col, communications_col, packages_col, custom_field_definitions_col, custom_field_values_col, custom_roles_col, custom_reports_col, fixed_assets_col, capital_projects_col, budgets_col, workflows_col, on_call_shifts_col, kb_articles_col, supplies_col, supply_orders_col, community_posts_col, repair_items_col, labor_rates_col, unit_baseline_photos_col, condition_reports_col, smart_lock_access_log_col, tour_slots_col, tour_bookings_col, market_rent_analyses_col, application_questions_col, gallery_photos_col, communication_templates_col, maintenance_schedules_col, accounting_connections_col, ai_actions_col
from routers import inspections, maintenance, ai_copilot, properties, leases, dashboard, auth, ai_actions, vendors, email_test, payments, notifications, social
from rate_limiter import limiter
from routers import condition_reports
from routers import market_rent
from routers import tours
from routers import smart_locks
from routers import accounting
from routers import vendor_acceptance
from routers import admin
from routers import leads
from routers import search
from routers import push
from routers import documents
from routers import gallery
from routers import owners
from routers import screening
from routers import reconciliation
from routers import public_listings
from routers import prospect_assistant
from routers import workflows
from routers import staff
from routers import maintenance_schedules
from routers import communications
from routers import resident_360
from routers import oncall
from routers import telephony
from routers import audit
from routers import budgets
from routers import kb
from routers import community
from routers import supplies
from routers import make_ready
from routers import repair_estimates
from routers import deposit_pipeline
from routers import capital_planning
from routers import diy_troubleshooting
from routers import rubs
from routers import custom_fields
from routers import communication_templates
from routers import custom_roles
from routers import write_assist
from routers import custom_views
from routers import bill_scan
from routers import lease_extract
from routers import ai_summaries
from routers import custom_reports
from routers import custom_rental_applications
from routers import trust_accounting
from routers import package_tracking
from routers import predictive_analytics
from routers import forms
from routers import scenario_ai
from routers import compliance
from routers import sms_inbound
from routers import portfolio_pricing
from routers import photo_upload
from routers import billing
from routers import organizations
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Replaces the old @app.on_event("startup") decorator - found
    during a comprehensive sweep that FastAPI's own test suite output
    already flagged on_event as deprecated in the FastAPI version this
    app runs on, in favor of this lifespan context-manager pattern.
    Safe to reference _migrate_legacy_data_to_default_org,
    rent_automation_scheduler, and vendor_sla_scheduler here even
    though they're defined further down in this same file - Python
    only looks up these names when this function actually RUNS (at
    real server startup, well after the whole module has finished
    loading), not when it's merely defined here - the exact same
    deferred-execution behavior the old on_event decorator already
    relied on.

    The `yield` is the real, correct place a shutdown step would go if
    this app ever needed one (closing a connection pool, flushing a
    queue) - there isn't one today, so nothing runs after it, but the
    contract point exists for real future use."""
    await _migrate_legacy_data_to_default_org()
    await ensure_indexes()
    asyncio.create_task(rent_automation_scheduler())
    asyncio.create_task(vendor_sla_scheduler())
    yield


app = FastAPI(title="PropWise AI API", lifespan=lifespan)

# Real rate limiting (slowapi) — genuinely missing before this,
# confirmed absent via a direct search of every existing endpoint.
# app.state.limiter is where slowapi's own decorator (@limiter.limit,
# applied directly on the specific endpoints that need it — see
# routers/auth.py's login/register and routers/payments.py's
# checkout/setup-intent) looks up its configuration at request time;
# the exception handler is what turns a triggered limit into a real,
# clean 429 response instead of an unhandled exception.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.middleware("http")
async def security_headers_middleware(request, call_next):
    """Real security headers, none of which existed before this -
    confirmed absent via a direct check of the only middleware
    previously registered (CORS). This is a JSON API, not a page-
    serving app, so a full page-oriented Content-Security-Policy
    (script-src, style-src, etc.) doesn't apply in the usual sense -
    but the headers below are genuinely relevant regardless:
    X-Frame-Options/frame-ancestors and X-Content-Type-Options guard
    against clickjacking and MIME-sniffing on any HTML this API does
    serve (notably /docs, the public Swagger UI - see the module
    docstring note on whether that should stay public in production),
    Referrer-Policy limits what leaks to third parties on any redirect
    or external link, and Permissions-Policy denies browser features
    this API has no legitimate reason to ever request."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    response.headers["Content-Security-Policy"] = "frame-ancestors 'none'"
    return response

# Adjust to your actual frontend origin(s) in production
# CHANGED Sept 13, 2026: a real custom domain (getpropwiseai.com) now
# exists and is verified/SSL-issued on Render - added alongside the
# existing onrender.com origin, not replacing it, since Render's
# "Render Subdomain" setting is still enabled and rentflow-ai-1.onrender.com
# remains a real, reachable origin for this same frontend. www is
# included too since Render's own custom-domain setup redirects it to
# the root domain, but a browser's initial request to www still
# originates from that host before the redirect completes.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "https://rentflow-ai-1.onrender.com", "https://getpropwiseai.com", "https://www.getpropwiseai.com"],
    allow_credentials=True,  # required for the new HttpOnly session cookie to be
                             # sent on cross-origin requests at all - browsers
                             # silently drop credentialed cookies otherwise. Only
                             # safe to combine with an explicit origin list (never
                             # "*") - already true above, confirmed before adding this.
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(inspections.router)
app.include_router(maintenance.router)
app.include_router(ai_copilot.router)
app.include_router(properties.router)
app.include_router(leases.router)
app.include_router(dashboard.router)
app.include_router(ai_actions.router)
app.include_router(vendors.router)
app.include_router(vendors.ticket_assign_router)
app.include_router(condition_reports.router)
app.include_router(market_rent.router)
app.include_router(tours.router)
app.include_router(smart_locks.router)
app.include_router(accounting.router)
app.include_router(vendor_acceptance.router)
app.include_router(email_test.router)
app.include_router(payments.router)
app.include_router(notifications.router)
app.include_router(social.router)
app.include_router(admin.router)
app.include_router(leads.router)
app.include_router(search.router)
app.include_router(push.router)
app.include_router(documents.router)
app.include_router(gallery.router)
app.include_router(owners.router)
app.include_router(screening.router)
app.include_router(reconciliation.router)
app.include_router(public_listings.router)
app.include_router(prospect_assistant.router)
app.include_router(workflows.router)
app.include_router(staff.router)
app.include_router(maintenance_schedules.router)
app.include_router(communications.router)
app.include_router(resident_360.router)
app.include_router(oncall.router)
app.include_router(telephony.router)
app.include_router(audit.router)
app.include_router(budgets.router)
app.include_router(kb.router)
app.include_router(community.router)
app.include_router(supplies.router)
app.include_router(make_ready.router)
app.include_router(repair_estimates.router)
app.include_router(deposit_pipeline.router)
app.include_router(capital_planning.router)
app.include_router(diy_troubleshooting.router)
app.include_router(rubs.router)
app.include_router(custom_fields.router)
app.include_router(communication_templates.router)
app.include_router(custom_roles.router)
app.include_router(write_assist.router)
app.include_router(custom_views.router)
app.include_router(bill_scan.router)
app.include_router(lease_extract.router)
app.include_router(ai_summaries.router)
app.include_router(custom_reports.router)
app.include_router(custom_rental_applications.router)
app.include_router(trust_accounting.router)
app.include_router(package_tracking.router)
app.include_router(predictive_analytics.router)
app.include_router(forms.router)
app.include_router(scenario_ai.router)
app.include_router(compliance.router)
app.include_router(sms_inbound.router)
app.include_router(portfolio_pricing.router)
app.include_router(photo_upload.router)
app.include_router(billing.router)
app.include_router(organizations.router)
# BUG FIX (found by actually running this): StaticFiles() raises at import
# time if the directory doesn't already exist on disk. On a fresh checkout
# there is no ./uploads folder yet, so the server would crash before it
# ever started. Create it if missing, and make the base path configurable
# to match UPLOAD_DIR used by routers/inspections.py (that's a subfolder
# of this one: UPLOAD_DIR defaults to "./uploads/inspection_photos").
UPLOAD_BASE_DIR = os.getenv("UPLOAD_BASE_DIR", "./uploads")
os.makedirs(UPLOAD_BASE_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_BASE_DIR), name="uploads")


logger = logging.getLogger("rentflow.scheduler")


async def _migrate_legacy_data_to_default_org():
    """One-time, idempotent migration for real data that existed before
    the multi-tenant organization layer - every user, property, and
    lease predating this change has no orgId at all. Genuinely
    necessary, not optional cleanup: without this, every org-scoped
    query added throughout the app would silently return nothing for
    this app's own existing, already-live data.

    BUG FIX: the original version only ran its body at all if it found
    a user still missing orgId. That was correct for the very first
    deploy of this migration, but broke the moment a LATER deploy
    added lease-backfill logic to this same function - by then every
    user already had orgId from the first run, so this early-return
    fired immediately and the new lease-backfill code never ran at
    all, confirmed directly via a live diagnostic endpoint showing
    leasesWithOrgId: 0 after that second deploy. Each collection now
    has its own independent "does this still need backfilling" check,
    so no single collection's already-migrated state can ever mask
    another collection genuinely still needing it - on any future
    startup, on any deploy, forever."""
    default_org = await organizations_col.find_one({"name": "Default Organization"})
    if not default_org:
        legacy_user = await users_col.find_one({"orgId": {"$exists": False}})
        if not legacy_user:
            return  # fresh install with no legacy data at all - nothing to migrate into
        from datetime import datetime, timezone
        result = await organizations_col.insert_one({
            "name": "Default Organization",
            "plan": "internal",  # this app's own real, pre-existing portfolio - never trial-gated
            "active": True,
            "createdAt": datetime.now(timezone.utc),
            "trialEndsAt": None,
        })
        org_id = str(result.inserted_id)
    else:
        org_id = str(default_org["_id"])

    user_result = await users_col.update_many({"orgId": {"$exists": False}}, {"$set": {"orgId": org_id}})
    property_result = await properties_col.update_many({"orgId": {"$exists": False}}, {"$set": {"orgId": org_id}})

    leases_missing_org = await leases_col.find({"orgId": {"$exists": False}}, {"_id": 1, "propertyId": 1}).to_list(length=10000)
    leases_updated = 0
    for lease in leases_missing_org:
        property_id = lease.get("propertyId")
        if not property_id:
            continue
        query_id = ObjectId(property_id) if ObjectId.is_valid(property_id) else property_id
        prop = await properties_col.find_one({"_id": query_id}, {"orgId": 1})
        if prop and prop.get("orgId"):
            await leases_col.update_one({"_id": lease["_id"]}, {"$set": {"orgId": prop["orgId"]}})
            leases_updated += 1

    tickets_missing_org = await tickets_col.find({"orgId": {"$exists": False}}, {"_id": 1, "propertyId": 1}).to_list(length=50000)
    tickets_updated = 0
    for ticket in tickets_missing_org:
        property_id = ticket.get("propertyId")
        if not property_id:
            continue
        query_id = ObjectId(property_id) if ObjectId.is_valid(property_id) else property_id
        prop = await properties_col.find_one({"_id": query_id}, {"orgId": 1})
        if prop and prop.get("orgId"):
            await tickets_col.update_one({"_id": ticket["_id"]}, {"$set": {"orgId": prop["orgId"]}})
            tickets_updated += 1

    vendor_result = await vendors_col.update_many({"orgId": {"$exists": False}}, {"$set": {"orgId": org_id}})

    payments_missing_org = await payments_col.find({"orgId": {"$exists": False}}, {"_id": 1, "propertyId": 1}).to_list(length=50000)
    payments_updated = 0
    for charge in payments_missing_org:
        property_id = charge.get("propertyId")
        if not property_id:
            continue
        query_id = ObjectId(property_id) if ObjectId.is_valid(property_id) else property_id
        prop = await properties_col.find_one({"_id": query_id}, {"orgId": 1})
        if prop and prop.get("orgId"):
            await payments_col.update_one({"_id": charge["_id"]}, {"$set": {"orgId": prop["orgId"]}})
            payments_updated += 1

    bank_lines_missing_org = await bank_lines_col.find({"orgId": {"$exists": False}}, {"_id": 1, "propertyId": 1}).to_list(length=50000)
    bank_lines_updated = 0
    for line in bank_lines_missing_org:
        property_id = line.get("propertyId")
        if not property_id:
            continue
        query_id = ObjectId(property_id) if ObjectId.is_valid(property_id) else property_id
        prop = await properties_col.find_one({"_id": query_id}, {"orgId": 1})
        if prop and prop.get("orgId"):
            await bank_lines_col.update_one({"_id": line["_id"]}, {"$set": {"orgId": prop["orgId"]}})
            bank_lines_updated += 1

    inspections_missing_org = await inspections_col.find({"orgId": {"$exists": False}}, {"_id": 1, "propertyId": 1}).to_list(length=50000)
    inspections_updated = 0
    for insp in inspections_missing_org:
        property_id = insp.get("propertyId")
        if not property_id:
            continue
        query_id = ObjectId(property_id) if ObjectId.is_valid(property_id) else property_id
        prop = await properties_col.find_one({"_id": query_id}, {"orgId": 1})
        if prop and prop.get("orgId"):
            await inspections_col.update_one({"_id": insp["_id"]}, {"$set": {"orgId": prop["orgId"]}})
            inspections_updated += 1

    documents_missing_org = await documents_col.find({"orgId": {"$exists": False}}, {"_id": 1, "leaseId": 1}).to_list(length=50000)
    documents_updated = 0
    for document in documents_missing_org:
        lease_id = document.get("leaseId")
        if not lease_id or not ObjectId.is_valid(lease_id):
            continue
        lease = await leases_col.find_one({"_id": ObjectId(lease_id)}, {"orgId": 1})
        if lease and lease.get("orgId"):
            await documents_col.update_one({"_id": document["_id"]}, {"$set": {"orgId": lease["orgId"]}})
            documents_updated += 1

    leads_missing_org = await leads_col.find({"orgId": {"$exists": False}}, {"_id": 1, "propertyId": 1}).to_list(length=50000)
    leads_updated = 0
    for lead in leads_missing_org:
        property_id = lead.get("propertyId")
        if not property_id:
            await leads_col.update_one({"_id": lead["_id"]}, {"$set": {"orgId": None}})
            continue
        query_id = ObjectId(property_id) if ObjectId.is_valid(property_id) else property_id
        prop = await properties_col.find_one({"_id": query_id}, {"orgId": 1})
        if prop and prop.get("orgId"):
            await leads_col.update_one({"_id": lead["_id"]}, {"$set": {"orgId": prop["orgId"]}})
            leads_updated += 1

    screening_missing_org = await screening_col.find({"orgId": {"$exists": False}}, {"_id": 1, "propertyId": 1}).to_list(length=50000)
    screening_updated = 0
    for req in screening_missing_org:
        property_id = req.get("propertyId")
        if not property_id:
            continue
        query_id = ObjectId(property_id) if ObjectId.is_valid(property_id) else property_id
        prop = await properties_col.find_one({"_id": query_id}, {"orgId": 1})
        if prop and prop.get("orgId"):
            await screening_col.update_one({"_id": req["_id"]}, {"$set": {"orgId": prop["orgId"]}})
            screening_updated += 1

    communications_missing_org = await communications_col.find({"orgId": {"$exists": False}}, {"_id": 1, "propertyId": 1}).to_list(length=50000)
    communications_updated = 0
    for comm in communications_missing_org:
        property_id = comm.get("propertyId")
        if not property_id:
            continue
        query_id = ObjectId(property_id) if ObjectId.is_valid(property_id) else property_id
        prop = await properties_col.find_one({"_id": query_id}, {"orgId": 1})
        if prop and prop.get("orgId"):
            await communications_col.update_one({"_id": comm["_id"]}, {"$set": {"orgId": prop["orgId"]}})
            communications_updated += 1

    packages_missing_org = await packages_col.find({"orgId": {"$exists": False}}, {"_id": 1, "propertyId": 1}).to_list(length=50000)
    packages_updated = 0
    for pkg in packages_missing_org:
        property_id = pkg.get("propertyId")
        if not property_id:
            continue
        query_id = ObjectId(property_id) if ObjectId.is_valid(property_id) else property_id
        prop = await properties_col.find_one({"_id": query_id}, {"orgId": 1})
        if prop and prop.get("orgId"):
            await packages_col.update_one({"_id": pkg["_id"]}, {"$set": {"orgId": prop["orgId"]}})
            packages_updated += 1

    custom_field_defs_result = await custom_field_definitions_col.update_many({"orgId": {"$exists": False}}, {"$set": {"orgId": org_id}})
    custom_field_values_result = await custom_field_values_col.update_many({"orgId": {"$exists": False}}, {"$set": {"orgId": org_id}})
    custom_roles_result = await custom_roles_col.update_many({"orgId": {"$exists": False}}, {"$set": {"orgId": org_id}})
    custom_reports_result = await custom_reports_col.update_many({"orgId": {"$exists": False}}, {"$set": {"orgId": org_id}})

    fixed_assets_missing_org = await fixed_assets_col.find({"orgId": {"$exists": False}}, {"_id": 1, "propertyId": 1}).to_list(length=50000)
    fixed_assets_updated = 0
    for asset in fixed_assets_missing_org:
        property_id = asset.get("propertyId")
        if not property_id:
            continue
        query_id = ObjectId(property_id) if ObjectId.is_valid(property_id) else property_id
        prop = await properties_col.find_one({"_id": query_id}, {"orgId": 1})
        if prop and prop.get("orgId"):
            await fixed_assets_col.update_one({"_id": asset["_id"]}, {"$set": {"orgId": prop["orgId"]}})
            fixed_assets_updated += 1

    capital_projects_missing_org = await capital_projects_col.find({"orgId": {"$exists": False}}, {"_id": 1, "propertyId": 1}).to_list(length=50000)
    capital_projects_updated = 0
    for project in capital_projects_missing_org:
        property_id = project.get("propertyId")
        if not property_id:
            continue
        query_id = ObjectId(property_id) if ObjectId.is_valid(property_id) else property_id
        prop = await properties_col.find_one({"_id": query_id}, {"orgId": 1})
        if prop and prop.get("orgId"):
            await capital_projects_col.update_one({"_id": project["_id"]}, {"$set": {"orgId": prop["orgId"]}})
            capital_projects_updated += 1

    budgets_missing_org = await budgets_col.find({"orgId": {"$exists": False}}, {"_id": 1, "propertyId": 1}).to_list(length=50000)
    budgets_updated = 0
    for budget in budgets_missing_org:
        property_id = budget.get("propertyId")
        if not property_id:
            continue
        query_id = ObjectId(property_id) if ObjectId.is_valid(property_id) else property_id
        prop = await properties_col.find_one({"_id": query_id}, {"orgId": 1})
        if prop and prop.get("orgId"):
            await budgets_col.update_one({"_id": budget["_id"]}, {"$set": {"orgId": prop["orgId"]}})
            budgets_updated += 1

    workflows_result = await workflows_col.update_many({"orgId": {"$exists": False}}, {"$set": {"orgId": org_id}})

    shifts_missing_org = await on_call_shifts_col.find({"orgId": {"$exists": False}}, {"_id": 1, "propertyIds": 1}).to_list(length=50000)
    shifts_updated = 0
    for shift in shifts_missing_org:
        for property_id in shift.get("propertyIds", []):
            query_id = ObjectId(property_id) if ObjectId.is_valid(property_id) else property_id
            prop = await properties_col.find_one({"_id": query_id}, {"orgId": 1})
            if prop and prop.get("orgId"):
                await on_call_shifts_col.update_one({"_id": shift["_id"]}, {"$set": {"orgId": prop["orgId"]}})
                shifts_updated += 1
                break

    kb_result = await kb_articles_col.update_many({"orgId": {"$exists": False}}, {"$set": {"orgId": org_id}})
    repair_items_result = await repair_items_col.update_many({"orgId": {"$exists": False}}, {"$set": {"orgId": org_id}})
    labor_rates_result = await labor_rates_col.update_many({"orgId": {"$exists": False}}, {"$set": {"orgId": org_id}})

    supplies_missing_org = await supplies_col.find({"orgId": {"$exists": False}}, {"_id": 1, "propertyId": 1}).to_list(length=50000)
    supplies_updated = 0
    for supply in supplies_missing_org:
        property_id = supply.get("propertyId")
        if not property_id:
            continue
        query_id = ObjectId(property_id) if ObjectId.is_valid(property_id) else property_id
        prop = await properties_col.find_one({"_id": query_id}, {"orgId": 1})
        if prop and prop.get("orgId"):
            await supplies_col.update_one({"_id": supply["_id"]}, {"$set": {"orgId": prop["orgId"]}})
            supplies_updated += 1

    supply_orders_missing_org = await supply_orders_col.find({"orgId": {"$exists": False}}, {"_id": 1, "propertyId": 1}).to_list(length=50000)
    supply_orders_updated = 0
    for order in supply_orders_missing_org:
        property_id = order.get("propertyId")
        if not property_id:
            continue
        query_id = ObjectId(property_id) if ObjectId.is_valid(property_id) else property_id
        prop = await properties_col.find_one({"_id": query_id}, {"orgId": 1})
        if prop and prop.get("orgId"):
            await supply_orders_col.update_one({"_id": order["_id"]}, {"$set": {"orgId": prop["orgId"]}})
            supply_orders_updated += 1

    community_posts_missing_org = await community_posts_col.find({"orgId": {"$exists": False}}, {"_id": 1, "propertyId": 1}).to_list(length=50000)
    community_posts_updated = 0
    for post in community_posts_missing_org:
        property_id = post.get("propertyId")
        if not property_id:
            continue
        query_id = ObjectId(property_id) if ObjectId.is_valid(property_id) else property_id
        prop = await properties_col.find_one({"_id": query_id}, {"orgId": 1})
        if prop and prop.get("orgId"):
            await community_posts_col.update_one({"_id": post["_id"]}, {"$set": {"orgId": prop["orgId"]}})
            community_posts_updated += 1

    async def _backfill_by_property(col, extra=0):
        missing = await col.find({"orgId": {"$exists": False}}, {"_id": 1, "propertyId": 1}).to_list(length=50000)
        updated = 0
        for doc in missing:
            property_id = doc.get("propertyId")
            if not property_id:
                continue
            query_id = ObjectId(property_id) if ObjectId.is_valid(property_id) else property_id
            prop = await properties_col.find_one({"_id": query_id}, {"orgId": 1})
            if prop and prop.get("orgId"):
                await col.update_one({"_id": doc["_id"]}, {"$set": {"orgId": prop["orgId"]}})
                updated += 1
        return updated

    baseline_photos_updated = await _backfill_by_property(unit_baseline_photos_col)
    condition_reports_updated = await _backfill_by_property(condition_reports_col)
    smart_lock_log_updated = await _backfill_by_property(smart_lock_access_log_col)
    tour_slots_updated = await _backfill_by_property(tour_slots_col)
    tour_bookings_updated = await _backfill_by_property(tour_bookings_col)
    market_rent_analyses_updated = await _backfill_by_property(market_rent_analyses_col)
    application_questions_updated = await _backfill_by_property(application_questions_col)
    gallery_photos_updated = await _backfill_by_property(gallery_photos_col)
    maintenance_schedules_updated = await _backfill_by_property(maintenance_schedules_col)

    # Communication templates and the (previously singleton) accounting
    # connection have no propertyId of their own - same flat stamp into
    # the default org as vendors/workflows above.
    communication_templates_result = await communication_templates_col.update_many({"orgId": {"$exists": False}}, {"$set": {"orgId": org_id}})
    accounting_connections_result = await accounting_connections_col.update_many({"orgId": {"$exists": False}}, {"$set": {"orgId": org_id}})

    # Real, genuine gap this closes: an organization created via the
    # legacy-data migration path above (rather than the real
    # signup_organization endpoint - see routers/auth.py) never had
    # ANY user marked isOrgOwner=True, since that flag is only ever
    # set on the specific account that runs through real signup.
    # Without this, billing (routers/billing.py) would be permanently
    # unreachable for that organization - no staff account could ever
    # manage it. Every real organization needs exactly one real owner,
    # guaranteed, not just ones created through signup. Idempotent and
    # narrow: only acts on an org that genuinely has zero owners, and
    # promotes its single earliest-created staff member - a real,
    # deterministic choice, not an arbitrary one, and the org's real
    # owner can always reassign this later via a future admin UI.
    owners_assigned = 0
    all_org_docs = await organizations_col.find({}, {"_id": 1}).to_list(length=1000)
    for org_doc in all_org_docs:
        this_org_id = str(org_doc["_id"])
        has_owner = await users_col.find_one({"orgId": this_org_id, "isOrgOwner": True}, {"_id": 1})
        if has_owner:
            continue
        earliest_staff = await users_col.find_one(
            {"orgId": this_org_id, "role": "staff"},
            sort=[("createdAt", 1)],
        )
        if earliest_staff:
            await users_col.update_one({"_id": earliest_staff["_id"]}, {"$set": {"isOrgOwner": True}})
            owners_assigned += 1

    # Same real per-property lookup as elsewhere above - an AI Action's
    # org is derived from its own real property when set. A handful of
    # actions may have no propertyId (a genuinely portfolio-wide
    # suggestion) - left alone rather than guessed at, same principle
    # as every other collection's unresolvable records above.
    ai_actions_missing_org = await ai_actions_col.find({"orgId": {"$exists": False}}, {"_id": 1, "propertyId": 1}).to_list(length=50000)
    ai_actions_updated = 0
    for action in ai_actions_missing_org:
        property_id = action.get("propertyId")
        if not property_id:
            continue
        query_id = ObjectId(property_id) if ObjectId.is_valid(property_id) else property_id
        prop = await properties_col.find_one({"_id": query_id}, {"orgId": 1})
        if prop and prop.get("orgId"):
            await ai_actions_col.update_one({"_id": action["_id"]}, {"$set": {"orgId": prop["orgId"]}})
            ai_actions_updated += 1

    if user_result.modified_count or property_result.modified_count or leases_updated or tickets_updated or vendor_result.modified_count or payments_updated or bank_lines_updated or inspections_updated or documents_updated or leads_updated or screening_updated or communications_updated or packages_updated or custom_field_defs_result.modified_count or custom_field_values_result.modified_count or custom_roles_result.modified_count or custom_reports_result.modified_count or fixed_assets_updated or capital_projects_updated or budgets_updated or workflows_result.modified_count or shifts_updated or kb_result.modified_count or repair_items_result.modified_count or labor_rates_result.modified_count or supplies_updated or supply_orders_updated or community_posts_updated or baseline_photos_updated or condition_reports_updated or smart_lock_log_updated or tour_slots_updated or tour_bookings_updated or market_rent_analyses_updated or application_questions_updated or gallery_photos_updated or maintenance_schedules_updated or communication_templates_result.modified_count or accounting_connections_result.modified_count or owners_assigned or ai_actions_updated:
        logger.info(
            f"[migration] Backfilled {user_result.modified_count} users, "
            f"{property_result.modified_count} properties, {leases_updated} leases, "
            f"{tickets_updated} tickets, {vendor_result.modified_count} vendors, "
            f"{payments_updated} payment charges, {bank_lines_updated} bank lines, "
            f"{inspections_updated} inspections, {documents_updated} documents, "
            f"{leads_updated} leads, {screening_updated} screening requests, "
            f"{communications_updated} communications, {packages_updated} packages, "
            f"{custom_field_defs_result.modified_count} custom field definitions, "
            f"{custom_field_values_result.modified_count} custom field values, "
            f"{custom_roles_result.modified_count} custom roles, "
            f"{custom_reports_result.modified_count} custom reports, "
            f"{fixed_assets_updated} fixed assets, {capital_projects_updated} capital projects, "
            f"{budgets_updated} budgets, {workflows_result.modified_count} workflows, "
            f"{shifts_updated} on-call shifts, {kb_result.modified_count} KB articles, "
            f"{repair_items_result.modified_count} repair items, {labor_rates_result.modified_count} labor rates, "
            f"{supplies_updated} supplies, {supply_orders_updated} supply orders, "
            f"{community_posts_updated} community posts, {baseline_photos_updated} baseline photos, "
            f"{condition_reports_updated} condition reports, {smart_lock_log_updated} smart lock log entries, "
            f"{tour_slots_updated} tour slots, {tour_bookings_updated} tour bookings, "
            f"{market_rent_analyses_updated} market rent analyses, "
            f"{application_questions_updated} application questions, {gallery_photos_updated} gallery photos, "
            f"{maintenance_schedules_updated} maintenance schedules, "
            f"{communication_templates_result.modified_count} communication templates, "
            f"{accounting_connections_result.modified_count} accounting connections, "
            f"{ai_actions_updated} AI actions, and {owners_assigned} organizations backfilled with a real owner "
            f"into default org {org_id}"
        )


async def rent_automation_scheduler():
    """The real, missing piece that makes these checks genuinely
    automated rather than merely automatable — no cron job or external
    scheduler existed anywhere in this project before this; every one
    of these checks only ever ran when someone manually called them.
    Runs as a background task inside this same process, no external
    infrastructure needed. Each run is wrapped in its own try/except so
    one check's failure doesn't kill the loop or block the others from
    running — and a genuinely unexpected exception here would otherwise
    silently stop all future automated runs forever, which is worse
    than one run failing loudly.

    Extended (Sept 2, 2026) from 2 checks to 6, then 7: confirmed
    directly by reading the code that lease renewal reminders, payment
    reminders, maintenance scheduling, and autopay were all fully built
    already and simply never wired into this loop, meaning they
    required a human (or an external cron service) to trigger every
    single time. The 7th (AI Actions auto-approve) is new logic, not
    a dormant existing check — deliberately narrow, see
    routers/ai_actions.py's _do_auto_approve_check for the actual
    eligibility rules. The admin key that gates admin.py's HTTP
    endpoints is deliberately bypassed here — this calls the internal
    _do_* helpers directly, same as late fee/escalation already did,
    since the key's purpose is authenticating an *external* trigger,
    not gating whether the check is allowed to run at all.

    Extended (Sept 3, 2026) with a lightweight heartbeat check (see
    scheduler_health.py) — a real, low-cost resilience improvement
    deliberately chosen over a full Celery + Redis migration for now:
    this app is still pre-launch, every check here is already safe to
    skip a cycle and catch up next run (idempotent, re-checks real
    current state), and a full task-queue migration needs a paid
    Background Worker + Redis instance this app doesn't need to carry
    yet. This just makes a missed cycle (from a Render restart/deploy)
    show up clearly in the logs instead of disappearing silently —
    real signal for if/when the bigger migration becomes worth it.

    Extended (Sept 3, 2026) again with the 8th check: staged renewal-
    risk outreach (90/60/30 days before lease expiry) — see
    renewal_risk_service.py and _do_renewal_risk_check's own
    docstrings for the real scoring reasoning and why this stays
    separate from the existing generic _do_lease_renewal_check."""
    from routers import admin as admin_router
    import scheduler_health
    interval_seconds = 6 * 60 * 60  # every 6 hours
    await scheduler_health.check_for_missed_cycle("rent_automation_scheduler", interval_seconds, logger)
    while True:
        try:
            result = await admin_router._do_late_fee_check()
            logger.info(f"[scheduler] late fee check: {result}")
        except Exception:
            logger.exception("[scheduler] late fee check failed")
        try:
            result = await admin_router._do_escalation_check()
            logger.info(f"[scheduler] escalation check: {result}")
        except Exception:
            logger.exception("[scheduler] escalation check failed")
        try:
            result = await admin_router._do_maintenance_check()
            logger.info(f"[scheduler] maintenance check: {result}")
        except Exception:
            logger.exception("[scheduler] maintenance check failed")
        try:
            result = await admin_router._do_lease_renewal_check()
            logger.info(f"[scheduler] lease renewal check: {result}")
        except Exception:
            logger.exception("[scheduler] lease renewal check failed")
        try:
            result = await admin_router._do_payment_reminder_check()
            logger.info(f"[scheduler] payment reminder check: {result}")
        except Exception:
            logger.exception("[scheduler] payment reminder check failed")
        try:
            result = await admin_router._do_autopay_check()
            logger.info(f"[scheduler] autopay check: {result}")
        except Exception:
            logger.exception("[scheduler] autopay check failed")
        try:
            from routers.ai_actions import _do_auto_approve_check
            result = await _do_auto_approve_check()
            logger.info(f"[scheduler] AI Actions auto-approve check: {result}")
        except Exception:
            logger.exception("[scheduler] AI Actions auto-approve check failed")
        try:
            result = await admin_router._do_renewal_risk_check()
            logger.info(f"[scheduler] renewal risk check: {result}")
        except Exception:
            logger.exception("[scheduler] renewal risk check failed")
        try:
            result = await admin_router._do_vendor_compliance_check()
            logger.info(f"[scheduler] vendor compliance check: {result}")
        except Exception:
            logger.exception("[scheduler] vendor compliance check failed")
        await scheduler_health.record_heartbeat("rent_automation_scheduler")
        await asyncio.sleep(interval_seconds)


async def vendor_sla_scheduler():
    """A genuinely separate, faster loop from rent_automation_scheduler
    above — deliberately NOT folded into that 6-hour cycle. The vendor
    SLA window itself defaults to 2 hours (see vendor_sla_service.py);
    checking on the same 6-hour cadence as late fees/lease renewals
    would silently let a vendor go unconfirmed for up to 8 hours
    before anything happened, undermining the entire premise of a
    "2-hour SLA." Runs every 15 minutes instead — frequent enough that
    the real escalation delay stays close to the actual configured
    SLA window, not bounded by an unrelated schedule chosen for
    entirely different, far less time-sensitive checks."""
    from routers import admin as admin_router
    import scheduler_health
    interval_seconds = 15 * 60  # every 15 minutes
    await scheduler_health.check_for_missed_cycle("vendor_sla_scheduler", interval_seconds, logger)
    while True:
        try:
            result = await admin_router._do_vendor_sla_check()
            logger.info(f"[scheduler] vendor SLA check: {result}")
        except Exception:
            logger.exception("[scheduler] vendor SLA check failed")
        await scheduler_health.record_heartbeat("vendor_sla_scheduler")
        await asyncio.sleep(interval_seconds)


@app.get("/api/health")
async def health():
    return {"status": "ok"}
