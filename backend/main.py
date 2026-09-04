"""
App entrypoint. If you already have a main.py, just copy the router
includes and the /uploads static mount into it — everything else here
(db, models, routers/*) drops into your existing project structure as-is.
"""
from dotenv import load_dotenv
load_dotenv()

import asyncio
import logging
from fastapi import FastAPI
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
import os
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from db import ensure_indexes
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
app = FastAPI(title="PropWise AI API")

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
# Still "rentflow-ai-1" despite the product being renamed to PropWise
# AI - Render's .onrender.com subdomain can't be changed after a
# service is created (confirmed directly, no dashboard workaround
# exists); see config.js's fuller note. Deliberately living with the
# old URL rather than migrating to a real custom domain for now.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "https://rentflow-ai-1.onrender.com"],
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


@app.on_event("startup")
async def on_startup():
    await ensure_indexes()
    asyncio.create_task(rent_automation_scheduler())
    asyncio.create_task(vendor_sla_scheduler())


@app.get("/api/health")
async def health():
    return {"status": "ok"}
