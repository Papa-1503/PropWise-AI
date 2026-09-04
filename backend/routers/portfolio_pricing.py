"""
Cross-building pricing comparison. See portfolio_pricing_service.py
for the full reasoning.

GET /api/portfolio-pricing/comparison  -> real per-building, per-
    bedroom-count rent gaps vs. the rest of the portfolio
"""
from fastapi import APIRouter, Depends

from auth import require_staff
import portfolio_pricing_service

router = APIRouter(prefix="/api/portfolio-pricing", tags=["portfolio-pricing"])


@router.get("/comparison")
async def get_pricing_comparison(user: dict = Depends(require_staff)):
    comparisons = await portfolio_pricing_service.compare_pricing_across_buildings()
    return {"comparisons": comparisons}
