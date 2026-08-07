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
@router.get("/diagnose-gallery")
async def diagnose_gallery(key: str = ""):
    expected = os.getenv("SEED_SECRET")
    if not expected:
        raise HTTPException(status_code=500, detail="SEED_SECRET is not configured")
    if key != expected:
        raise HTTPException(status_code=403, detail="Invalid key")

    env_check = {
        "CLOUDINARY_CLOUD_NAME_set": bool(os.getenv("CLOUDINARY_CLOUD_NAME")),
        "CLOUDINARY_API_KEY_set": bool(os.getenv("CLOUDINARY_API_KEY")),
        "CLOUDINARY_API_SECRET_set": bool(os.getenv("CLOUDINARY_API_SECRET")),
    }

    import cloudinary
    import cloudinary.uploader
    from io import BytesIO
    import base64

    cloudinary.config(
        cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
        api_key=os.getenv("CLOUDINARY_API_KEY"),
        api_secret=os.getenv("CLOUDINARY_API_SECRET"),
        secure=True,
    )

    tiny_png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )

    try:
        result = cloudinary.uploader.upload(
            BytesIO(tiny_png),
            folder="rentflow/diagnostics",
            resource_type="image",
        )
        return {"env_check": env_check, "cloudinary_upload": "SUCCESS", "url": result["secure_url"]}
    except Exception as exc:
        return {"env_check": env_check, "cloudinary_upload": "FAILED", "error": str(exc)}
