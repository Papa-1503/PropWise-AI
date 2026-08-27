"""
Shared ticket severity scoring, used by both the public ticket-creation
endpoint (routers/maintenance.py) and workflow-triggered ticket creation
(services/workflow_actions.py) — the same two separate code paths that
needed the shared duplicate-detection helper (services/ticket_dedup.py).

Deliberately simple and rule-based (same "transparent, not a statistical
model" philosophy as the applicant screening score and vendor
recommendation score elsewhere in this app): keyword tiers on the
ticket's title text, plus a small category-based baseline, combined into
a 0-100 score with a human-readable explanation.

Two things intentionally left out of this first version, both flagged
during design review rather than silently omitted:
- No tenant-vulnerability input (e.g. "elderly", "infant") as a scoring
  factor. Real fair-housing concern — a system that treats one
  resident's ticket as more urgent than another's based on personal
  characteristics is exactly the kind of differential treatment that
  invites legal risk, however well-intentioned. If this is wanted later,
  it needs its own careful discussion, not a quiet addition here.
- No weather-data integration (e.g. boosting "no heat" severity based on
  outside temperature). Real value, but a genuinely new external
  dependency this app doesn't have anywhere else — worth its own
  deliberate build, not folded into this one.
"""

import re

# Tiered keyword lists. Checked in order — emergency keywords win over
# urgent, which win over low, so a title matching multiple tiers gets the
# most severe one. Word-boundary matching (not raw substring) so e.g.
# "heat" doesn't also match inside an unrelated word.
EMERGENCY_KEYWORDS = [
    "no heat", "no water", "gas smell", "gas leak", "flooding", "flood",
    "fire", "smoke", "carbon monoxide", "sewage", "electrical spark",
    "exposed wire", "sparking",
]
URGENT_KEYWORDS = [
    "no ac", "ac not", "air conditioning not", "broken lock", "won't lock",
    "can't lock", "refrigerator", "fridge", "leak", "leaks", "leaking",
    "no hot water", "won't flush", "power outage", "outlet not working",
    "electrical", "break-in", "security",
]
LOW_KEYWORDS = [
    "cosmetic", "paint", "scuff", "touch up", "touch-up", "squeaky",
    "wipe down", "clean", "aesthetic",
]

# Categories that are inherently higher-stakes when something goes wrong
# (a plumbing failure floods a unit; a landscaping issue rarely does) —
# a small baseline nudge, not a hard override of the keyword match.
CATEGORY_BASELINE = {
    "electrical": 10,
    "plumbing": 8,
    "hvac": 6,
    "locksmith": 5,
    "general": 0,
    "landscaping": -5,
}


def _matches_any(title_lower: str, keywords: list[str]) -> str | None:
    for kw in keywords:
        if re.search(r"\b" + re.escape(kw) + r"\b", title_lower):
            return kw
    return None


def compute_severity(title: str, category: str | None) -> dict:
    """Returns {"score": int 0-100, "tier": str, "explanation": str}.
    Never raises — a scoring failure should default to a safe middle
    tier rather than block ticket creation."""
    try:
        title_lower = (title or "").lower()

        emergency_hit = _matches_any(title_lower, EMERGENCY_KEYWORDS)
        urgent_hit = _matches_any(title_lower, URGENT_KEYWORDS) if not emergency_hit else None
        low_hit = _matches_any(title_lower, LOW_KEYWORDS) if not emergency_hit and not urgent_hit else None

        baseline = CATEGORY_BASELINE.get(category or "general", 0)

        if emergency_hit:
            score = min(100, 90 + baseline)
            tier = "emergency"
            explanation = f'Matched emergency keyword "{emergency_hit}"'
        elif urgent_hit:
            score = min(89, 65 + baseline)
            tier = "urgent"
            explanation = f'Matched urgent keyword "{urgent_hit}"'
        elif low_hit:
            score = max(0, 15 + baseline)
            tier = "low"
            explanation = f'Matched low-severity keyword "{low_hit}"'
        else:
            score = max(0, min(59, 40 + baseline))
            tier = "routine"
            explanation = "No severity keywords matched — default routine tier"

        if baseline:
            explanation += f", {category} category ({'+' if baseline > 0 else ''}{baseline})"

        return {"score": score, "tier": tier, "explanation": explanation}
    except Exception:
        return {"score": 40, "tier": "routine", "explanation": "Scoring unavailable — defaulted to routine"}
