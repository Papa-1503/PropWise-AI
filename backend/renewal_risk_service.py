"""
Renewal risk scoring — a real, explainable weighted formula over this
lease's actual payment and maintenance history, not a trained
statistical model. Same honesty pattern already established elsewhere
in this app (routers/vendors.py's recommended_vendors composite score,
the dashboard health score): a transparent, justifiable heuristic
staff can actually understand and argue with, not a black box.

IMPORTANT: this is Claude's/this app's reasoned estimate from real
portfolio data, not an actuarial model trained on actual historical
renewal outcomes — there's no historical "did this resident actually
renew" dataset in this app yet to validate against. Treat the score as
a real, useful signal for WHERE to focus renewal outreach, not a
guaranteed prediction. Building genuine predictive validation would
mean tracking real renewal outcomes over time and checking whether
this score's ranking actually correlated with them — real, separate
future work once enough renewal cycles have passed to have that data.

Score is 0-100, higher = more at risk of not renewing. Three real,
grounded factors:
  1. Payment reliability (0-40 pts) — % of this lease's own charges
     that ever had a late fee applied or were escalated.
  2. Maintenance satisfaction (0-35 pts) — this unit's average
     satisfactionRating on closed, rated tickets (inverted: a low
     rating means real, stated dissatisfaction).
  3. Current open tickets (0-25 pts) — how many real, currently-open
     maintenance issues this unit has right now, a live pain signal
     distinct from historical satisfaction.
Missing data for a factor scores as a neutral midpoint, not a penalty
or a reward — a lease with no maintenance history at all shouldn't be
flagged as either especially safe or especially risky on that factor.
"""
from datetime import datetime, timezone

from db import payments_col, tickets_col

MAX_PAYMENT_POINTS = 40
MAX_SATISFACTION_POINTS = 35
MAX_OPEN_TICKETS_POINTS = 25

RISK_THRESHOLDS = {"low": 30, "medium": 60}  # score < 30 = low, 30-59 = medium, 60+ = high


def _risk_level(score: float) -> str:
    if score < RISK_THRESHOLDS["low"]:
        return "low"
    if score < RISK_THRESHOLDS["medium"]:
        return "medium"
    return "high"


async def compute_renewal_risk(lease: dict) -> dict:
    """Real, live computation over this lease's actual charges and this
    unit's actual tickets — nothing pre-aggregated or cached, so the
    score always reflects current, real state."""
    property_id = lease.get("propertyId")
    unit_id = lease.get("unitId")

    # ---- Factor 1: payment reliability ----
    charges = await payments_col.find({"propertyId": property_id, "unitId": unit_id}).to_list(length=500)
    if charges:
        troubled = sum(1 for c in charges if c.get("lateFeeApplied") or c.get("escalated"))
        late_rate = troubled / len(charges)
        payment_points = round(late_rate * MAX_PAYMENT_POINTS, 1)
        payment_detail = f"{troubled} of {len(charges)} charges had a late fee or were escalated ({late_rate*100:.0f}%)"
    else:
        payment_points = MAX_PAYMENT_POINTS / 2
        payment_detail = "No payment history on file yet"

    # ---- Factor 2: maintenance satisfaction ----
    rated_tickets = await tickets_col.find({
        "propertyId": property_id, "unitId": unit_id, "satisfactionRating": {"$exists": True},
    }).to_list(length=200)
    if rated_tickets:
        avg_rating = sum(t["satisfactionRating"] for t in rated_tickets) / len(rated_tickets)
        # rating 5 (best) -> 0 points, rating 1 (worst) -> full points
        satisfaction_points = round(((5 - avg_rating) / 4) * MAX_SATISFACTION_POINTS, 1)
        satisfaction_detail = f"Average maintenance satisfaction: {avg_rating:.1f}/5 across {len(rated_tickets)} rated ticket(s)"
    else:
        satisfaction_points = MAX_SATISFACTION_POINTS / 2
        satisfaction_detail = "No rated maintenance tickets on file yet"

    # ---- Factor 3: currently open tickets ----
    open_tickets = await tickets_col.count_documents({
        "propertyId": property_id, "unitId": unit_id, "status": {"$ne": "done"},
    })
    # 4+ open tickets hits the full point cap - a real, if arbitrary,
    # ceiling rather than letting one unusually ticket-heavy unit
    # dominate the whole score.
    open_points = round(min(open_tickets, 4) / 4 * MAX_OPEN_TICKETS_POINTS, 1)
    open_detail = f"{open_tickets} currently open maintenance ticket(s)"

    total = round(payment_points + satisfaction_points + open_points, 1)

    return {
        "score": total,
        "riskLevel": _risk_level(total),
        "factors": [
            {"name": "Payment reliability", "points": payment_points, "maxPoints": MAX_PAYMENT_POINTS, "detail": payment_detail},
            {"name": "Maintenance satisfaction", "points": satisfaction_points, "maxPoints": MAX_SATISFACTION_POINTS, "detail": satisfaction_detail},
            {"name": "Currently open tickets", "points": open_points, "maxPoints": MAX_OPEN_TICKETS_POINTS, "detail": open_detail},
        ],
    }


def days_until(end_date, now: datetime | None = None) -> int | None:
    """Real, timezone-safe day count until a lease's endDate. Returns
    None for anything that isn't a real datetime, rather than raising —
    callers treat that as "can't evaluate this lease right now"."""
    if not isinstance(end_date, datetime):
        return None
    now = now or datetime.now(timezone.utc)
    end_naive = end_date.replace(tzinfo=None) if end_date.tzinfo else end_date
    now_naive = now.replace(tzinfo=None) if now.tzinfo else now
    return (end_naive - now_naive).days
