"""
AI summaries (P18).

GET /api/ai-summaries/ticket/{ticket_id}  -> a real, grounded summary of
                                              one ticket's full history

Deliberately scoped to maintenance tickets first, the entity in this
app with the most genuinely summarizable real history in one place:
time entries (who worked on it, how long, what they noted), satisfaction
rating/comment if the resident has submitted one, and current status -
all real, already-stored fields, not fabricated. Grounded the same way
every other AI feature in this app is: the real data is handed to the
model as context, with an explicit instruction never to invent a fact
not present in it.
"""
import os

from fastapi import APIRouter, HTTPException, Depends
from anthropic import AsyncAnthropic
from bson import ObjectId

from db import tickets_col
from auth import require_staff

router = APIRouter(prefix="/api/ai-summaries", tags=["ai-summaries"])

anthropic_client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
MODEL = "claude-sonnet-4-6"


@router.get("/ticket/{ticket_id}")
async def summarize_ticket(ticket_id: str, user: dict = Depends(require_staff)):
    if not ObjectId.is_valid(ticket_id):
        raise HTTPException(status_code=400, detail="Invalid ticket ID")
    ticket = await tickets_col.find_one({"_id": ObjectId(ticket_id)})
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    time_entries = ticket.get("timeEntries", [])
    if not time_entries and not ticket.get("satisfactionRating"):
        return {"summary": "No time entries or resident feedback recorded yet - nothing substantial to summarize.", "grounded": False}

    time_entry_text = "\n".join(
        f"- {e.get('hours')}h logged by {e.get('loggedBy', 'unknown')}: {e.get('note') or '(no note)'}"
        for e in time_entries
    ) or "No time entries logged."

    satisfaction_text = "No resident feedback yet."
    if ticket.get("satisfactionRating"):
        satisfaction_text = f"Resident rated the resolution {ticket['satisfactionRating']}/5"
        if ticket.get("satisfactionComment"):
            satisfaction_text += f": \"{ticket['satisfactionComment']}\""

    context_text = (
        f"Ticket: {ticket.get('title')}\n"
        f"Unit: {ticket.get('unitId')} | Category: {ticket.get('category')} | Status: {ticket.get('status')}\n"
        f"Total hours logged: {ticket.get('totalHours', 0)}\n\n"
        f"TIME ENTRIES:\n{time_entry_text}\n\n"
        f"RESIDENT FEEDBACK:\n{satisfaction_text}"
    )

    if not os.getenv("ANTHROPIC_API_KEY"):
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY is not configured")

    system_prompt = (
        "Summarize this maintenance ticket's history in 2-4 sentences for a staff member "
        "reviewing it. Use ONLY the real data given below - never invent a detail, a date, "
        "or a name not actually present in it. Be specific about what was actually done "
        "(from the time entry notes), not generic.\n\n"
        f"{context_text}"
    )

    try:
        response = await anthropic_client.messages.create(
            model=MODEL,
            max_tokens=250,
            system=system_prompt,
            messages=[{"role": "user", "content": "Summarize this ticket."}],
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI backend error: {exc}") from exc

    summary_text = "".join(
        block.text for block in response.content if getattr(block, "type", None) == "text"
    )

    return {"summary": summary_text, "grounded": True}
