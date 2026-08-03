"""
App entrypoint. If you already have a main.py, just copy the router
includes and the /uploads static mount into it — everything else here
(db, models, routers/*) drops into your existing project structure as-is.
"""
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
import os
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from db import ensure_indexes
from routers import inspections, maintenance, ai_copilot, properties, leases, dashboard, auth, ai_actions, vendors, email_test, payments, notifications, social

app = FastAPI(title="RentFlow AI API")

# Adjust to your actual frontend origin(s) in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
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

# BUG FIX (found by actually running this): StaticFiles() raises at import
# time if the directory doesn't already exist on disk. On a fresh checkout
# there is no ./uploads folder yet, so the server would crash before it
# ever started. Create it if missing, and make the base path configurable
# to match UPLOAD_DIR used by routers/inspections.py (that's a subfolder
# of this one: UPLOAD_DIR defaults to "./uploads/inspection_photos").
UPLOAD_BASE_DIR = os.getenv("UPLOAD_BASE_DIR", "./uploads")
os.makedirs(UPLOAD_BASE_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_BASE_DIR), name="uploads")


@app.on_event("startup")
async def on_startup():
    await ensure_indexes()


@app.get("/api/health")
async def health():
    return {"status": "ok"}
