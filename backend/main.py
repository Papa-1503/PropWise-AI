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
import os
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from db import ensure_indexes
from routers import inspections, maintenance, ai_copilot, properties, leases, dashboard, auth, ai_actions, vendors, email_test, payments, notifications, social
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
from routers import workflows
from routers import staff
from routers import maintenance_schedules
from routers import communications
from routers import resident_360
from routers import oncall
app = FastAPI(title="RentFlow AI API")

# Adjust to your actual frontend origin(s) in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "https://rentflow-ai-1.onrender.com"],
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
app.include_router(workflows.router)
app.include_router(staff.router)
app.include_router(maintenance_schedules.router)
app.include_router(communications.router)
app.include_router(resident_360.router)
app.include_router(oncall.router)
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
    """The real, missing piece that makes the late-fee and escalation
    checks genuinely automated rather than merely automatable — no cron
    job or external scheduler existed anywhere in this project before
    this; both checks only ever ran when someone manually called them
    (including during testing today). Runs as a background task inside
    this same process, no external infrastructure needed. Each run is
    wrapped in its own try/except so one check's failure doesn't kill
    the loop or block the other check from running — and a genuinely
    unexpected exception here would otherwise silently stop all future
    automated runs forever, which is worse than one run failing loudly."""
    from routers import admin as admin_router
    interval_seconds = 6 * 60 * 60  # every 6 hours
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
        await asyncio.sleep(interval_seconds)


@app.on_event("startup")
async def on_startup():
    await ensure_indexes()
    asyncio.create_task(rent_automation_scheduler())


@app.get("/api/health")
async def health():
    return {"status": "ok"}
