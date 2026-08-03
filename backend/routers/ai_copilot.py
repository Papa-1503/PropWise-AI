"""
AI Copilot endpoint.

POST /api/ai/copilot

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
from models import CopilotRequest, CopilotResponse
from auth import get_current_user

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

    # Vacant units (assumes properties_col stores unit-level occupancy;
    # adjust the field names to match your actual schema)
    vacant_cursor = properties_col.find({**prop_query, "units.status": "vacant"})
    vacant = await vacant_cursor.to_list(length=50)
    if vacant:
        sources.append("properties.db")
        lines = []
        for p in vacant:
            for u in p.get("units", []):
                if u.get("status") == "vacant":
                    lines.append(f"- {p.get('name', p.get('propertyId'))} unit {u.get('unitId')}")
        sections.append("VACANT UNITS:\n" + "\n".join(lines[:20]))

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
        "You are RentFlow AI's operations copilot for property management staff. "
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
