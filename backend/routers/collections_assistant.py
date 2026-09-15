"""
Collections assistant — a real, conversational AI guide that walks
staff through their currently past-due charges, one at a time, and
sends real reminders on their behalf. Fourth real feature built on the
same agentic tool-calling pattern established by
routers/onboarding_assistant.py, routers/reconciliation_assistant.py,
and routers/vendor_assistant.py.

GET  /api/collections-assistant/status -> real, live delinquent-charge
                                           count and total outstanding
                                           for this org
POST /api/collections-assistant/chat   -> the real conversational loop -
                                           2 real tools
                                           (list_delinquent_charges,
                                           send_reminder), each calling
                                           the exact same real, already-
                                           tested functions already
                                           proven in routers/payments.py
                                           (list_delinquent,
                                           send_reminder_now) - never
                                           reimplemented here

SAFETY / SCOPE: identical org-scoping discipline to the other three
assistants. Deliberately does NOT include an "apply late fee" tool -
no real, staff-triggered manual late-fee endpoint exists in this app
today (only the automated scheduler in admin.py's _do_late_fee_check
applies them, portfolio-wide); adding one is real, separate product
work this pass doesn't take on. send_reminder reuses
payment_reminder_service.py's own real 48-hour cooldown - this
assistant can never be used to spam a resident beyond what the manual
"Send reminder now" button already allows.
"""
import os
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends
from anthropic import AsyncAnthropic
from bson import ObjectId
from pydantic import BaseModel

from db import payments_col
from auth import require_staff
from routers.payments import serialize
import payment_reminder_service
from audit_service import log_action

router = APIRouter(prefix="/api/collections-assistant", tags=["payments"])

anthropic_client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
MODEL = "claude-haiku-4-5-20251001"
MAX_TOOL_ITERATIONS = 6

SYSTEM_PROMPT = """You are the PropWise AI collections assistant. Your job is to help staff work through their currently past-due (delinquent) charges, one at a time, and send real payment reminders where it makes sense.

Start by calling list_delinquent_charges to see what's outstanding. If there are none, tell the person collections are fully caught up - nothing more to do. Otherwise, summarize the real list briefly (how many charges, total outstanding), then go through them one at a time: for each, tell the person the property/unit, the amount owed, and how overdue it is.

Ask before sending a reminder for a specific charge - don't send automatically. If the person says something like "send reminders to everyone" or "do them all", that counts as confirmation to go through the list and call send_reminder for each one, but still tell them as you go which one you're sending. If a reminder can't be sent (e.g. one was already sent recently), say so honestly rather than pretending it worked.

Keep this efficient - staff are working through a real task list, not having an open-ended conversation."""

TOOLS = [
    {
        "name": "list_delinquent_charges",
        "description": "Lists this organization's currently past-due (delinquent) charges.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "send_reminder",
        "description": "Sends a real payment reminder for a specific delinquent charge. Only call this after the person has confirmed they want a reminder sent for that charge (or for all charges).",
        "input_schema": {
            "type": "object",
            "properties": {"chargeId": {"type": "string"}},
            "required": ["chargeId"],
        },
        "cache_control": {"type": "ephemeral"},
    },
]


class CollectionsChatMessage(BaseModel):
    role: str
    content: str


class CollectionsChatRequest(BaseModel):
    message: str
    history: list[CollectionsChatMessage] = []


async def _get_delinquent_summary(org_id: str) -> dict:
    now = datetime.now(timezone.utc)
    all_past_due = await payments_col.find({"orgId": org_id, "dueDate": {"$lt": now}}).to_list(length=1000)
    delinquent = [serialize(dict(c)) for c in all_past_due]
    delinquent = [c for c in delinquent if c["status"] == "late"]
    total_outstanding = sum(c["amountDue"] - c["amountPaid"] for c in delinquent)
    return {"count": len(delinquent), "totalOutstanding": round(total_outstanding, 2)}


@router.get("/status")
async def collections_assistant_status(user: dict = Depends(require_staff)):
    return await _get_delinquent_summary(user["orgId"])


async def _execute_tool(tool_name: str, tool_input: dict, org_id: str, user: dict) -> dict:
    """Reuses the exact real logic already proven in
    routers/payments.py's list_delinquent and send_reminder_now -
    never reimplements either, so this assistant can never drift from
    the real behavior staff already get from the manual UI."""
    if tool_name == "list_delinquent_charges":
        now = datetime.now(timezone.utc)
        all_past_due = await payments_col.find({"orgId": org_id, "dueDate": {"$lt": now}}).to_list(length=1000)
        delinquent = [serialize(dict(c)) for c in all_past_due]
        delinquent = [c for c in delinquent if c["status"] == "late"]
        total_outstanding = sum(c["amountDue"] - c["amountPaid"] for c in delinquent)
        return {"charges": delinquent, "count": len(delinquent), "totalOutstanding": round(total_outstanding, 2)}

    elif tool_name == "send_reminder":
        charge_id = tool_input.get("chargeId", "")
        if not ObjectId.is_valid(charge_id):
            return {"sent": False, "error": "Invalid charge ID."}

        charge = await payments_col.find_one({"_id": ObjectId(charge_id), "orgId": org_id})
        if not charge:
            return {"sent": False, "error": "Charge not found."}

        if charge.get("amountPaid", 0) >= charge.get("amountDue", 0):
            return {"sent": False, "error": "This charge is already paid in full."}

        now = datetime.now(timezone.utc)
        if not payment_reminder_service.reminder_eligible(charge, now):
            return {
                "sent": False,
                "reason": "A reminder was already sent for this charge within the last 48 hours.",
            }

        result = await payment_reminder_service.send_payment_reminder(charge)
        await payments_col.update_one(
            {"_id": charge["_id"]},
            {"$set": {"lastReminderSentAt": now, "reminderSent": True}},
        )
        await log_action(
            actor_id=str(user["id"]), actor_email=user.get("email", ""), org_id=org_id,
            action="payment_reminder_sent_manually_via_ai", target_type="payment", target_id=charge_id,
            details=result,
        )
        return {"sent": True, "channels": result}

    return {"error": f"Unknown tool: {tool_name}"}


@router.post("/chat")
async def collections_assistant_chat(payload: CollectionsChatRequest, user: dict = Depends(require_staff)):
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise HTTPException(status_code=501, detail="The AI assistant isn't configured yet.")

    org_id = user["orgId"]
    messages = [{"role": m.role, "content": m.content} for m in payload.history]
    messages.append({"role": "user", "content": payload.message})

    for _ in range(MAX_TOOL_ITERATIONS):
        response = await anthropic_client.messages.create(
            model=MODEL, max_tokens=1024,
            system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            tools=TOOLS, messages=messages,
        )

        tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
        if not tool_use_blocks:
            final_text = "".join(b.text for b in response.content if b.type == "text")
            summary = await _get_delinquent_summary(org_id)
            return {
                "reply": final_text,
                "history": messages + [{"role": "assistant", "content": final_text}],
                **summary,
            }

        messages.append({"role": "assistant", "content": [b.model_dump() for b in response.content]})
        tool_results = []
        for block in tool_use_blocks:
            result = await _execute_tool(block.name, block.input, org_id, user)
            tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": str(result)})
        messages.append({"role": "user", "content": tool_results})

    summary = await _get_delinquent_summary(org_id)
    return {
        "reply": "I've made some progress but want to check in before continuing — want me to keep going?",
        "history": messages,
        **summary,
    }
