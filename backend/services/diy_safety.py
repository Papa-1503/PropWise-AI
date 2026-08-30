"""
AI-guided DIY troubleshooting eligibility gate (P20).

Real, code-level safety boundary, checked BEFORE any AI call is ever
made - the PDF's own design note flagged this exact requirement:
"needs a real safety boundary, not just relying on the AI to naturally
avoid unsafe suggestions." This module is that boundary. If a ticket's
title matches anything here, DIY guidance is never offered - full
stop, no AI call happens at all for that ticket, regardless of how the
prompt might be worded. The AI is never given the chance to be
talked into suggesting something unsafe, because it's never invoked
for these categories in the first place.

DANGER_KEYWORDS below is deliberately broad and conservative - when in
doubt, exclude. A resident missing out on a DIY suggestion for
something that was actually safe is a minor inconvenience; a resident
being guided to attempt gas line work, open an electrical panel, or
work on anything structural is a real safety risk this app has no
business enabling, however well-worded the AI's caveats might be.

Reuses the exact word-boundary regex pattern already established in
ticket_severity.py rather than a different matching mechanism for a
second, closely-related keyword-based safety decision.
"""
import re

DANGER_KEYWORDS = [
    # Multi-word phrases, checked as exact phrases first (fast, precise)
    "gas leak", "gas line", "gas valve", "gas smell", "smell of gas",
    "smell gas", "gas odor",
    "electrical panel", "breaker box", "exposed wire", "electrical spark",
    "circuit breaker panel",
    "foundation crack", "load bearing", "load-bearing", "ceiling collapse",
    "wall collapse", "sagging roof", "sagging ceiling", "ceiling sagging",
    "roof sagging", "ceiling is sagging",
    "smoke detector going off", "carbon monoxide", "co detector", "co alarm",
    "sewage backup",
]

# Single, unambiguous danger words - deliberately kept separate from
# the phrase list above and matched independently (any ONE of these
# present anywhere is enough to exclude), rather than requiring an
# exact multi-word phrase that real ticket titles won't reliably use
# in one fixed order. Real bug this fixes, caught by testing against
# genuinely varied phrasing rather than only the phrasing used to
# write the original list: "smell of gas near the stove" and "ceiling
# looks like its sagging" both failed to match the original phrase-
# only list, since real word order doesn't always match how a keyword
# phrase happens to be written.
DANGER_WORDS = [
    "gas", "sparking", "wiring", "rewire", "structural", "foundation",
    "sagging", "fire", "smoke", "sewage", "flooding", "flood",
]

SAFE_DIY_KEYWORDS = [
    "tripped breaker", "reset breaker", "flipped breaker",
    "loose handle", "loose doorknob", "thermostat not responding",
    "wifi thermostat", "smart thermostat",
]


def _matches_any(text_lower: str, keywords: list[str]) -> str | None:
    for kw in keywords:
        if re.search(r"\b" + re.escape(kw) + r"\b", text_lower):
            return kw
    return None


def check_diy_eligibility(title: str, description: str = "") -> dict:
    """Returns {"eligible": bool, "reason": str}. Checked against both
    title and description text combined, since a dangerous detail could
    appear in either. This function makes the real, final decision -
    callers must never offer DIY guidance, or invoke the AI to generate
    it, when eligible is False."""
    combined = f"{title} {description}".lower()

    safe_match = _matches_any(combined, SAFE_DIY_KEYWORDS)
    if safe_match:
        return {"eligible": True, "reason": f"Matches a known-safe self-help scenario ('{safe_match}')."}

    danger_match = _matches_any(combined, DANGER_KEYWORDS) or _matches_any(combined, DANGER_WORDS)
    if danger_match:
        return {
            "eligible": False,
            "reason": f"This involves '{danger_match}', which is not appropriate for self-help guidance. "
                      "This has been routed directly to maintenance.",
        }

    return {"eligible": True, "reason": "No known safety concern detected for this issue."}
