"""
One-off admin endpoint to trigger the demo simulation seed data without
needing shell access (not available on Render's free tier). Protected
by a shared secret in the URL, not staff auth, since it's meant to be
visited directly in a browser once. Safe to leave in place — running it
again just skips anything that already exists (see seed_property_data.py).
"""
import os
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/seed-demo")
async def seed_demo(key: str = ""):
    expected = os.getenv("SEED_SECRET")
    if not expected:
        raise HTTPException(status_code=500, detail="SEED_SECRET is not configured")
    if key != expected:
        raise HTTPException(status_code=403, detail="Invalid key")

    from scripts.seed_property_data import seed
    await seed()
    return {"status": "done", "message": "Simulation data seeded. Refresh the app to see it."}
