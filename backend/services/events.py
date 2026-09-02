"""
Workflow event dispatcher.

Call emit_event(...) from any router after an action happens (e.g. a unit
is created) to check for published workflows listening for that event and
run their actions.
"""
import time
from datetime import datetime, timezone

from db import workflows_col, workflow_runs_col
from services.workflow_actions import ACTION_HANDLERS


def _conditions_match(conditions: dict | None, payload: dict) -> bool:
    if not conditions:
        return True
    return all(payload.get(k) == v for k, v in conditions.items())


async def emit_event(event_name: str, payload: dict):
    cursor = workflows_col.find({
        "trigger.event": event_name,
        "status": "published",
    })
    workflows = await cursor.to_list(length=100)
    for workflow in workflows:
        if _conditions_match(workflow["trigger"].get("conditions"), payload):
            await execute_workflow(workflow, payload)


async def execute_workflow(workflow: dict, payload: dict):
    """CHANGED (Sept 2, 2026): now records real per-step timing
    (durationMs), not just an overall run start/finish - the genuinely
    missing piece needed to show a real execution timeline (see
    WorkflowRunFlow.jsx on the frontend) with actual measured durations
    per action, not fabricated or estimated ones. Each step's
    durationMs is measured with time.monotonic() around that one
    handler call specifically, so a slow email provider or a failing
    webhook shows up as a real, attributable number on that one step,
    not blended into the total."""
    run_log = {
        "workflowId": str(workflow["_id"]),
        "triggerEvent": workflow["trigger"]["event"],
        "startedAt": datetime.now(timezone.utc),
        "steps": [],
    }

    actions = sorted(workflow.get("actions", []), key=lambda a: a["order"])
    for action in actions:
        handler = ACTION_HANDLERS.get(action["type"])
        if not handler:
            run_log["steps"].append({
                "action": action["type"], "order": action["order"],
                "status": "skipped", "error": "no handler registered", "durationMs": 0,
            })
            continue
        step_start = time.monotonic()
        try:
            result = await handler(action.get("config", {}), payload)
            duration_ms = round((time.monotonic() - step_start) * 1000)
            run_log["steps"].append({
                "action": action["type"], "order": action["order"],
                "status": "success", "result": result, "durationMs": duration_ms,
            })
        except Exception as e:
            duration_ms = round((time.monotonic() - step_start) * 1000)
            run_log["steps"].append({
                "action": action["type"], "order": action["order"],
                "status": "failed", "error": str(e), "durationMs": duration_ms,
            })
            break

    run_log["finishedAt"] = datetime.now(timezone.utc)
    await workflow_runs_col.insert_one(run_log)
