"""
After-hours voice triage — the AI conversation logic behind
routers/telephony.py's phone-answering flow.

Deliberately built on Twilio's <Gather input="speech"> turn-based
exchange, not real-time Media Streams - a turn-based Q&A needs no new
persistent infrastructure (no WebSocket server, no speech-to-speech
model), reusing only what this app already has real, working
credentials for (Twilio Voice, already-verified webhook signing). A
live, talk-over-each-other phone conversation would need that new
infrastructure - real, deliberately out of scope for this pass.

Same "AI decides what to ask, real code decides the numbers/rules"
split already established elsewhere in this app: this module ONLY
decides what to say and when the conversation has gathered enough to
create a ticket. It never scores severity itself - the caller's
propertyId/unitId/title/description flow into the exact same
deterministic services/ticket_severity.py every other ticket in this
app is scored by (see routers/telephony.py's use of
routers.maintenance.create_ticket_document).
"""
import os
import json

from anthropic import AsyncAnthropic

anthropic_client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
MODEL = "claude-sonnet-4-6"

# The very first question is asked immediately, with no AI call needed -
# lower latency for the caller, and one fewer real API call per call
# received. The AI only starts deciding things from the caller's first
# answer onward.
FIRST_QUESTION = "Hi, this is the after-hours maintenance line. What's going on, and which unit are you calling about?"

# Hard cap on how many questions the AI can ask (in addition to the
# fixed first one) - bounds call length and real API cost, and gives
# every caller a guaranteed end to the conversation even if the model
# never confidently concludes on its own.
MAX_FOLLOWUP_QUESTIONS = 2

_SYSTEM_PROMPT_TEMPLATE = """You are triaging an after-hours maintenance phone call for a property management company. Have a brief, natural conversation to gather what's wrong and which unit it's in. Ask at most one short question per turn - never more than one question in a single response.

{unit_context}

{conclude_instruction}

Respond with ONLY JSON, no prose, no markdown fences:
{{
  "action": "ask" or "conclude",
  "question": "<next spoken question, one short sentence>" or null,
  "title": "<short plain title for a maintenance ticket, e.g. 'Kitchen sink leaking'>" or null,
  "description": "<a few sentences summarizing what the caller described>" or null,
  "category": "plumbing" or "electrical" or "hvac" or "general" or "landscaping" or "locksmith" or null,
  "unitId": "<unit number if the caller stated one this call, else null>"
}}

Use action "conclude" once you genuinely know what's wrong (title/description/category must all be set then). Use "ask" only if you still need one more piece of information (question must be set then, title/description/category should be null)."""


def _build_system_prompt(known_unit: str | None, force_conclude: bool) -> str:
    unit_context = (
        f"The caller's unit is already known: {known_unit}. Do not ask for it again."
        if known_unit
        else "The caller's unit is not yet known - ask for it if they haven't already said which unit they're in."
    )
    conclude_instruction = (
        "You must conclude now with whatever information you have gathered so far, even if incomplete "
        "- do not ask another question."
        if force_conclude
        else f"You may ask up to {MAX_FOLLOWUP_QUESTIONS} follow-up questions total before you must conclude."
    )
    return _SYSTEM_PROMPT_TEMPLATE.format(unit_context=unit_context, conclude_instruction=conclude_instruction)


def _fallback_conclude(turns: list[dict]) -> dict:
    """Used only if the model's response can't be parsed as the
    expected JSON - a real, if crude, safe default (conclude with
    whatever the caller actually said, verbatim) rather than either
    crashing the call or looping forever waiting for a well-formed
    response that isn't coming."""
    combined = " ".join(t.get("answer", "") for t in turns if t.get("answer"))
    return {
        "action": "conclude",
        "question": None,
        "title": (combined[:80] or "After-hours call - details unclear"),
        "description": combined or "Caller's description could not be captured clearly.",
        "category": "general",
        "unitId": None,
    }


async def next_step(turns: list[dict], known_unit: str | None) -> dict:
    """turns: list of {"question": str, "answer": str} already
    exchanged this call, oldest first. Returns the parsed decision
    dict (see _SYSTEM_PROMPT_TEMPLATE's JSON shape). Never raises -
    any real failure (API error, malformed JSON) falls back to
    concluding with what was actually said, since a phone call has no
    good way to show an error message and must always end somewhere."""
    force_conclude = len(turns) >= MAX_FOLLOWUP_QUESTIONS + 1  # +1 for the fixed first question

    messages = []
    for turn in turns:
        messages.append({"role": "assistant", "content": turn["question"]})
        messages.append({"role": "user", "content": turn.get("answer") or "(no response)"})

    try:
        response = await anthropic_client.messages.create(
            model=MODEL,
            max_tokens=300,
            system=_build_system_prompt(known_unit, force_conclude),
            messages=messages,
        )
        raw_text = "".join(block.text for block in response.content if getattr(block, "type", None) == "text")
        result = json.loads(raw_text)
        if result.get("action") not in ("ask", "conclude"):
            raise ValueError("unexpected action")
        if force_conclude:
            result["action"] = "conclude"
        return result
    except Exception:
        return _fallback_conclude(turns)
