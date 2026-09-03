"""
24/7 leasing assistant for prospects — the single most commonly cited
AI ROI feature in current (2026) property-management market research
(AppFolio's own reported figure: cuts leasing staff workload ~14
hours/week). Answers real prospect questions about vacant units using
only real, grounded data — never invents pricing, policies, or
availability — and points toward the existing real actions a prospect
can already take (book a self-guided tour, leave contact info).

PUBLIC — no auth, matches the existing public pattern already
established by /api/leads and /api/tours/slots. A prospect asking
"is this pet friendly?" before they're any kind of account holder is
exactly the case this app's public endpoints already exist for.

FAIR HOUSING — read before touching this file. This talks directly to
real members of the public applying for housing, which is squarely
within the highest-stakes real-world application of the Fair Housing
Act (and applicable state/local law): discriminatory statements or
steering based on race, color, religion, sex, familial status
(including pregnancy or having children), national origin, or
disability are illegal, not just a bad look. The system prompt below
is a real, load-bearing legal safeguard, not boilerplate — it must
never be weakened, and any future change to this file should re-read
it in full before touching the prompt.
"""
import os
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from anthropic import AsyncAnthropic
from bson import ObjectId

from db import properties_col, tour_slots_col
from models import ProspectChatRequest, CopilotResponse

router = APIRouter(prefix="/api/public", tags=["public"])

anthropic_client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
MODEL = "claude-sonnet-4-6"


async def _gather_prospect_context(property_id: str | None) -> str:
    """Real, grounded context: currently-vacant units (with whatever
    real leasing-info fields staff have actually set — see
    PropertyUpdate's petPolicy/parkingInfo/utilitiesIncluded), plus
    real open, bookable tour slots for each. Deliberately excludes
    EVERYTHING about existing residents (names, lease terms, payment
    history) — a prospect-facing endpoint has no legitimate reason to
    ever see or reason about that data, and it must never leak into
    what an AI model answering the public is given as context."""
    prop_filter = {}
    if property_id:
        query_id = ObjectId(property_id) if ObjectId.is_valid(property_id) else property_id
        prop_filter = {"_id": query_id}
    cursor = properties_col.find(prop_filter)
    properties = await cursor.to_list(length=200)

    now = datetime.now(timezone.utc)
    sections = []

    for p in properties:
        vacant_units = [u for u in p.get("units", []) if u.get("status") == "vacant"]
        if not vacant_units:
            continue

        pid = str(p["_id"])
        lines = [f"BUILDING: {p.get('name', 'Unnamed property')}"]
        if p.get("address"):
            lines.append(f"Address: {p['address']}")
        if p.get("petPolicy"):
            lines.append(f"Pet policy: {p['petPolicy']}")
        if p.get("parkingInfo"):
            lines.append(f"Parking: {p['parkingInfo']}")
        if p.get("utilitiesIncluded"):
            lines.append(f"Utilities included: {p['utilitiesIncluded']}")

        lines.append("Vacant units:")
        for u in vacant_units:
            unit_line = (
                f"  - Unit {u.get('unitId')}: ${u.get('rent', 0):,.0f}/month, "
                f"{u.get('bedrooms', 0)} bed / {u.get('bathrooms', 0)} bath"
            )
            if u.get("squareFootage"):
                unit_line += f", {u['squareFootage']:,.0f} sqft"
            lines.append(unit_line)

            slots_cursor = tour_slots_col.find({
                "propertyId": pid, "unitId": u.get("unitId"), "startTime": {"$gt": now},
            }).sort("startTime", 1).limit(5)
            slots = await slots_cursor.to_list(length=5)
            open_slots = [s for s in slots if s.get("bookedCount", 0) < s.get("capacity", 1)]
            if open_slots:
                slot_strs = [s["startTime"].strftime("%A %B %d at %I:%M %p") for s in open_slots[:3]]
                lines.append(f"    Open tour slots: {', '.join(slot_strs)}")
            else:
                lines.append("    No tour slots currently open for this unit — suggest contacting the office to schedule one.")

        sections.append("\n".join(lines))

    return "\n\n".join(sections) if sections else "No vacant units are currently listed."


@router.post("/prospect-chat", response_model=CopilotResponse)
async def prospect_chat(payload: ProspectChatRequest):
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY is not configured")

    context_text = await _gather_prospect_context(payload.propertyId)

    system_prompt = f"""You are a leasing assistant answering questions from a prospective
renter on a public apartment-listing chat, available 24/7. Answer ONLY using the real,
current CONTEXT below — never invent rent prices, availability, policies, or amenities
not stated there. If the context doesn't have what's needed to answer, say so plainly
and suggest they leave their contact info or reach out to the leasing office directly —
never guess.

FAIR HOUSING (mandatory, no exceptions): You are legally required to treat every
prospective renter identically. NEVER ask about, comment on, or let your answer be
influenced in any way by a prospect's race, color, religion, sex, familial status
(including pregnancy or having children), national origin, disability, or any other
protected characteristic under the Fair Housing Act or applicable state/local law —
even if the prospect brings it up themselves. Never steer a prospect toward or away
from any unit, floor, or building based on anything other than the objective criteria
they explicitly state (budget, bedroom count, move-in date). Answering a real, factual
question about a building's physical accessibility features (e.g. "is there an
elevator?") is fine and helpful when the context has that information — the
requirement is that you never treat any prospect differently, or make assumptions
about what they want or qualify for, based on a protected characteristic. If a
question asks you to make a judgment call outside this scope, direct them to the
leasing office rather than guessing.

Be warm, concise, and specific. When relevant, mention that a self-guided tour can be
booked directly, and note real open tour slots from the context if any exist.

CONTEXT:
{context_text}"""

    messages = [{"role": t.role, "content": t.content} for t in payload.history]
    messages.append({"role": "user", "content": payload.message})

    try:
        response = await anthropic_client.messages.create(
            model=MODEL,
            max_tokens=400,
            system=system_prompt,
            messages=messages,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI backend error: {exc}") from exc

    answer_text = "".join(
        block.text for block in response.content if getattr(block, "type", None) == "text"
    )

    return CopilotResponse(answer=answer_text, sources=["current vacancy listings", "tour availability"])
