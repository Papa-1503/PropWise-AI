"""
Workflow event dispatcher.

Call emit_event(...) from any router after an action happens (e.g. a unit
is created) to check for published workflows listening for that event and
run their actions.
"""
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
                "action": action["type"],
                "status": "skipped",
                "error": "no handler registered",
            })
            continue
        try:
            result = await handler(action.get("config", {}), payload)
            run_log["steps"].append({
                "action": action["type"], "status": "success", "result": result
            })
        except Exception as e:
            run_log["steps"].append({
                "action": action["type"], "status": "failed", "error": str(e)
            })
            break

    run_log["finishedAt"] = datetime.now(timezone.utc)
    await workflow_runs_col.insert_one(run_log)
