"""
Compliance calendar — real deadlines computed from staff-configured
per-property rules. See compliance_calendar_service.py for the full
reasoning, especially why this app never hardcodes actual state law.

GET /api/compliance/calendar?propertyId=  -> real upcoming deadlines
"""
from fastapi import APIRouter, Depends

from auth import require_staff
import compliance_calendar_service

router = APIRouter(prefix="/api/compliance", tags=["compliance"])


@router.get("/calendar")
async def get_compliance_calendar(propertyId: str | None = None, user: dict = Depends(require_staff)):
    property_ids = [propertyId] if propertyId else None
    deadlines = await compliance_calendar_service.get_upcoming_deadlines(user["orgId"], property_ids)
    return {"deadlines": deadlines}
