"""
AI Copilot endpoint.

POST /api/ai/copilot
POST /api/ai/faq     -> lightweight tenant-facing auto-responder, real
                        data only (that resident's own lease and
                        maintenance tickets), never the broader
                        staff-scoped context /copilot uses

Pulls live context from Mongo (vacant units, leases expiring soon, recent
inspection flags, open maintenance tickets), hands that to Claude along
with the conversation history, and returns a grounded answer plus which
data sources it drew from.

Requires ANTHROPIC_API_KEY to be set in the environment.
"""
import os
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Depends
from anthropic import AsyncAnthropic

from db import tickets_col, inspections_col, leases_col, properties_col
from models import CopilotRequest, CopilotResponse, FaqRequest
from auth import get_current_user, require_staff
import translation_service

router = APIRouter(prefix="/api/ai", tags=["ai"])

anthropic_client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
MODEL = "claude-sonnet-4-6"


async def gather_context(property_id: str | None) -> tuple[str, list[str]]:
    """
    Pulls a small, relevant slice of live data rather than the whole
    database, and returns it as plain text for the prompt plus a list
    of which collections were touched (for the 'sources' field in the response).
    """
    sources: list[str] = []
    sections: list[str] = []

    prop_query = {"propertyId": property_id} if property_id else {}

    # Vacant units - confirmed against the real live database this
    # session (13 of the app's properties genuinely have vacant units
    # right now) that units.status="vacant" is the correct, real query
    # shape for this collection - the original comment here
    # speculating the field names might need adjusting was written
    # before that was ever verified. Kept explicit and counted, not
    # just listed, so this section can't be mistaken for absent by
    # either the model or a person skimming the raw context.
    vacant_cursor = properties_col.find({**prop_query, "units.status": "vacant"})
    vacant = await vacant_cursor.to_list(length=50)
    if vacant:
        sources.append("properties.db")
        lines = []
        for p in vacant:
            for u in p.get("units", []):
                if u.get("status") == "vacant":
                    lines.append(f"- {p.get('name', p.get('propertyId'))} unit {u.get('unitId')}")
        sections.append(f"VACANT UNITS ({len(lines)} total):\n" + "\n".join(lines[:20]))
    else:
        # Explicit "genuinely zero" statement, not silent omission -
        # the model should never have to infer "no section shown" as
        # "no data available" versus "this data source wasn't
        # checked," which is exactly the ambiguity that led to an
        # honest-sounding but wrong "I don't have vacancy data"
        # answer.
        sections.append("VACANT UNITS: none currently (checked live, this is a real zero, not missing data).")
        sources.append("properties.db")

    # Leases expiring in the next 60 days
    cutoff = datetime.now(timezone.utc) + timedelta(days=60)
    lease_query = {**prop_query, "endDate": {"$lte": cutoff}}
    leases = await leases_col.find(lease_query).sort("endDate", 1).to_list(length=50)
    if leases:
        sources.append("leases.db")
        lines = [
            f"- Unit {l.get('unitId')}: {l.get('residentName', 'unknown')} expires "
            f"{l.get('endDate').strftime('%b %d, %Y') if l.get('endDate') else 'unknown'}, "
            f"renewal status: {l.get('renewalStatus', 'not sent')}"
            for l in leases
        ]
        sections.append("LEASES EXPIRING WITHIN 60 DAYS:\n" + "\n".join(lines[:20]))

    # Recent inspections with flagged/failed items
    recent_cutoff = datetime.now(timezone.utc) - timedelta(days=14)
    insp_query = {**prop_query, "createdAt": {"$gte": recent_cutoff}}
    inspections = await inspections_col.find(insp_query).sort("createdAt", -1).to_list(length=30)
    if inspections:
        sources.append("inspections.db")
        lines = []
        for insp in inspections:
            flagged = [i for i in insp.get("items", []) if i.get("status") in ("flag", "fail")]
            if flagged:
                descs = "; ".join(i.get("description", i.get("room", "")) for i in flagged)
                lines.append(f"- Unit {insp.get('unitId')} ({insp.get('type')}): {descs}")
        if lines:
            sections.append("RECENT INSPECTION FLAGS (last 14 days):\n" + "\n".join(lines[:20]))

    # Open maintenance tickets
    ticket_query = {**prop_query, "status": {"$ne": "done"}}
    tickets = await tickets_col.find(ticket_query).sort("createdAt", -1).to_list(length=50)
    if tickets:
        sources.append("maintenance.db")
        lines = [
            f"- #{str(t['_id'])[-4:]} [{t.get('priority')}] {t.get('title')} — unit {t.get('unitId')}, status: {t.get('status')}"
            for t in tickets
        ]
        sections.append("OPEN MAINTENANCE TICKETS:\n" + "\n".join(lines[:30]))

    context_text = "\n\n".join(sections) if sections else "No relevant records found."
    return context_text, sources


@router.post("/copilot", response_model=CopilotResponse)
async def ask_copilot(payload: CopilotRequest, user: dict = Depends(get_current_user)):
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY is not configured")

    context_text, sources = await gather_context(payload.propertyId)

    system_prompt = (
        "You are PropWise AI's operations copilot for property management staff. "
        "Answer only using the CONTEXT below, which was just pulled live from the database. "
        "Be specific and concise — cite unit numbers and counts. "
        "If the context doesn't contain what's needed to answer, say so plainly rather than guessing.\n\n"
        f"CONTEXT:\n{context_text}"
    )

    messages = [{"role": t.role, "content": t.content} for t in payload.history]
    messages.append({"role": "user", "content": payload.message})

    try:
        response = await anthropic_client.messages.create(
            model=MODEL,
            max_tokens=500,
            system=system_prompt,
            messages=messages,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI backend error: {exc}") from exc

    answer_text = "".join(
        block.text for block in response.content if getattr(block, "type", None) == "text"
    )

    return CopilotResponse(answer=answer_text, sources=sources)


async def _gather_tenant_context(user: dict) -> str:
    """Scoped strictly to the authenticated tenant's own unit - never
    accepts propertyId/unitId from the request, only ever reads them
    off the server-verified user record. Pulls the tenant's own lease
    (rent, dates, renewal status) and their own open/recent maintenance
    tickets - real, honest context this resident is actually entitled
    to see, nothing about any other unit or resident."""
    property_id = user.get("propertyId")
    unit_id = user.get("unitId")
    sections = []

    if property_id and unit_id:
        lease = await leases_col.find_one({"propertyId": property_id, "unitId": unit_id})
        if lease:
            sections.append(
                f"Your lease: unit {unit_id}, rent ${lease.get('rent', 0):,.2f}/month, "
                f"term {lease.get('startDate')} to {lease.get('endDate')}, "
                f"renewal status: {lease.get('renewalStatus', 'not_sent')}."
            )

        tickets = await tickets_col.find({"propertyId": property_id, "unitId": unit_id}).sort("createdAt", -1).limit(10).to_list(length=10)
        if tickets:
            ticket_lines = [f"  - {t.get('title', 'Untitled')}: {t.get('status', 'unknown')}" for t in tickets]
            sections.append("Your recent maintenance requests:\n" + "\n".join(ticket_lines))

    if not sections:
        return "No lease or maintenance information is on file for this account yet."
    return "\n\n".join(sections)


@router.post("/faq", response_model=CopilotResponse)
async def tenant_faq(payload: FaqRequest, user: dict = Depends(get_current_user)):
    """Lightweight tenant-facing auto-responder - answers common
    questions instantly using only that tenant's own real data (lease
    terms, their own maintenance ticket status), ahead of a full
    tenant-facing chatbot (a separate, larger Notion backlog item).
    Deliberately narrow context, not the broader staff-copilot context
    (vacancy counts, other units' leases) - a resident should never be
    able to see that regardless of what they ask."""
    if user.get("role") != "tenant":
        raise HTTPException(status_code=403, detail="This endpoint is for tenant accounts.")

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY is not configured")

    context_text = await _gather_tenant_context(user)

    system_prompt = (
        "You are PropWise AI's resident help assistant. Answer only using the CONTEXT "
        "below, which is this specific resident's own real lease and maintenance "
        "information. Be friendly, brief, and specific. If the context doesn't contain "
        "what's needed to answer a question, say so plainly and suggest contacting the "
        "property office rather than guessing at policies or information not provided "
        "here.\n\n"
        f"CONTEXT:\n{context_text}"
        f"{translation_service.language_instruction(user.get('preferredLanguage'))}"
    )

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

    return CopilotResponse(answer=answer_text, sources=["your lease", "your maintenance requests"])


@router.get("/vacant-units")
async def get_vacant_units(propertyId: str | None = None, user: dict = Depends(require_staff)):
    """A real, dedicated, structured endpoint for exactly the question
    a manager or authorized staff member actually asks: 'show me
    vacant units for this property.' Doesn't depend on the general-
    purpose copilot's context-gathering or the AI model correctly
    inferring the right answer from a blended context blob - this
    queries the real, confirmed-correct units.status='vacant' shape
    directly and returns real structured data every time, the same
    honest source of truth gather_context above now also uses.
    Scoped to a specific property when propertyId is given, or across
    every property otherwise - real per-property or portfolio-wide
    vacancy visibility, not one or the other."""
    prop_query = {"propertyId": propertyId} if propertyId else {}
    cursor = properties_col.find({**prop_query, "units.status": "vacant"})
    properties_with_vacancies = await cursor.to_list(length=200)

    results = []
    for p in properties_with_vacancies:
        for u in p.get("units", []):
            if u.get("status") == "vacant":
                results.append({
                    "propertyId": p.get("_id"),
                    "propertyName": p.get("name"),
                    "unitId": u.get("unitId"),
                    "rent": u.get("rent"),
                    "bedrooms": u.get("bedrooms"),
                    "bathrooms": u.get("bathrooms"),
                    "readyToList": u.get("readyToList", True),
                })

    return {"vacantUnitCount": len(results), "vacantUnits": results}
