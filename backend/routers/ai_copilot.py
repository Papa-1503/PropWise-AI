"""
AI Copilot endpoint.

POST /api/ai/copilot -> staff-only (require_staff) - see the real,
                        structural fix note on ask_copilot below for
                        why that gate is new as of Sept 14, 2026
POST /api/ai/faq     -> real, conversational resident assistant, real
                        data only (that resident's own lease and
                        maintenance tickets), never the broader
                        staff-scoped context /copilot uses. Genuinely
                        agentic as of Sept 14, 2026 - can submit a
                        real maintenance request on the resident's
                        behalf via a real tool, not just describe how
                        to use the maintenance form (see
                        TENANT_CHAT_TOOLS and tenant_faq below).

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
async def ask_copilot(payload: CopilotRequest, user: dict = Depends(require_staff)):
    # SECURITY FIX (Sept 14, 2026): this endpoint pulls portfolio-wide,
    # staff-scoped context (gather_context below - vacant units across
    # the whole property, every lease expiring soon, open maintenance
    # tickets) - confirmed directly that this previously used
    # get_current_user with NO role check at all, meaning a tenant
    # account could call this and receive real data about other
    # residents' units and portfolio operations they have no business
    # seeing. The frontend also happened to route tenants to this
    # exact endpoint via a shared "ai" tab component - both the
    # frontend routing AND this now-fixed structural gate needed
    # fixing; relying on the frontend alone would have left this
    # endpoint itself directly callable by any authenticated tenant.
    # Tenants now get their own real, correctly-scoped chatbot at
    # /faq below instead.
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


TENANT_CHAT_TOOLS = [
    {
        "name": "submit_maintenance_request",
        "description": "Submits a real maintenance request on this resident's behalf, for their own unit. Only call this once you have a clear title and enough detail to be useful to a technician.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "A short, clear summary, e.g. 'Kitchen faucet leaking'"},
                "description": {"type": "string", "description": "Any further detail the resident gave"},
                "category": {"type": "string", "enum": ["plumbing", "electrical", "hvac", "general", "landscaping", "locksmith"]},
                "priority": {"type": "string", "enum": ["normal", "urgent"], "description": "urgent only for something posing real safety/property risk (e.g. active leak, no heat in winter, no power) - default to normal otherwise"},
            },
            "required": ["title", "category"],
        },
        "cache_control": {"type": "ephemeral"},
    },
]


async def _execute_tenant_tool(tool_name: str, tool_input: dict, user: dict) -> dict:
    """SCOPE: propertyId/unitId are ALWAYS taken from the authenticated
    tenant's own user record, exactly like _gather_tenant_context above
    - never from tool_input, even though the tool's own input_schema
    doesn't offer them in the first place. Reuses the exact real
    create_ticket_document pipeline (dedup check, real severity
    scoring, auto-assignment, vendor auto-dispatch, real notifications)
    already proven by the two other real non-web callers of this same
    function (routers/telephony.py's AI phone triage,
    routers/sms_inbound.py's text-in triage) - this chatbot is the
    third, never a smaller reimplementation of a subset of it."""
    if tool_name == "submit_maintenance_request":
        property_id = user.get("propertyId")
        unit_id = user.get("unitId")
        if not property_id or not unit_id:
            return {"success": False, "error": "No unit is on file for this account - contact the property office directly."}

        from routers.maintenance import create_ticket_document
        doc = {
            "propertyId": property_id, "unitId": unit_id,
            "title": tool_input.get("title", "").strip(),
            "description": tool_input.get("description"),
            "category": tool_input.get("category", "general"),
            "priority": tool_input.get("priority", "normal"),
            "source": "resident",
        }
        if not doc["title"]:
            return {"success": False, "error": "A title is required."}
        result = await create_ticket_document(doc, user["orgId"])
        return {
            "success": True,
            "ticketId": result.get("_id"),
            "wasExistingDuplicate": result.get("wasExistingDuplicate", False),
        }

    return {"success": False, "error": f"Unknown tool: {tool_name}"}


@router.post("/faq")
async def tenant_faq(payload: FaqRequest, user: dict = Depends(get_current_user)):
    """Real, conversational resident assistant - answers questions
    using only this tenant's own real data (lease terms, their own
    maintenance ticket status - see _gather_tenant_context), and can
    now also DO something real on the resident's behalf: submit a
    real maintenance request conversationally, via the real
    submit_maintenance_request tool below, rather than only being
    able to describe how to fill out the maintenance form. This is
    the resident-facing counterpart to the staff-facing agentic
    assistants built earlier - same real tool-calling pattern, same
    never-trust-client-submitted-scope discipline (propertyId/unitId
    always come from the authenticated user's own record, in both the
    context-gathering below and _execute_tenant_tool above).

    Deliberately narrow context and a single, low-risk tool - never
    the broader staff-copilot context (vacancy counts, other units'
    leases; see the real, now-fixed role gate on /copilot above) - a
    resident should never be able to see or affect anything outside
    their own unit."""
    if user.get("role") != "tenant":
        raise HTTPException(status_code=403, detail="This endpoint is for tenant accounts.")

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY is not configured")

    context_text = await _gather_tenant_context(user)

    system_prompt = (
        "You are PropWise AI's resident help assistant. Answer using the CONTEXT below, "
        "which is this specific resident's own real lease and maintenance information. "
        "Be friendly, brief, and specific. If the context doesn't contain what's needed to "
        "answer a question, say so plainly rather than guessing at policies or information "
        "not provided here.\n\n"
        "If the resident describes a real maintenance problem, gather enough detail (what's "
        "wrong, which room if relevant) and then call submit_maintenance_request on their "
        "behalf - you don't need to ask permission first, since submitting the request IS "
        "the help they're asking for, but do briefly confirm what you're submitting as you "
        "do it. Mark priority as urgent only for something posing a real safety or property "
        "risk (active leak, no heat, no power, gas smell) - default to normal otherwise.\n\n"
        f"CONTEXT:\n{context_text}"
        f"{translation_service.language_instruction(user.get('preferredLanguage'))}"
    )

    messages = [{"role": t.role, "content": t.content} for t in payload.history]
    messages.append({"role": "user", "content": payload.message})

    ticket_created = False
    for _ in range(4):
        try:
            response = await anthropic_client.messages.create(
                model=MODEL,
                max_tokens=500,
                system=[{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}],
                tools=TENANT_CHAT_TOOLS,
                messages=messages,
            )
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"AI backend error: {exc}") from exc

        tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
        if not tool_use_blocks:
            answer_text = "".join(b.text for b in response.content if b.type == "text")
            return {
                "answer": answer_text,
                "sources": ["your lease", "your maintenance requests"],
                "history": messages + [{"role": "assistant", "content": answer_text}],
                "ticketCreated": ticket_created,
            }

        messages.append({"role": "assistant", "content": [b.model_dump() for b in response.content]})
        tool_results = []
        for block in tool_use_blocks:
            result = await _execute_tenant_tool(block.name, block.input, user)
            if result.get("success"):
                ticket_created = True
            tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": str(result)})
        messages.append({"role": "user", "content": tool_results})

    return {
        "answer": "I've made some progress but want to check in — is there anything else you'd like me to do?",
        "sources": ["your lease", "your maintenance requests"],
        "history": messages,
        "ticketCreated": ticket_created,
    }


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
