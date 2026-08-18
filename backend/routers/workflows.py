"""
Workflow automation endpoints.

GET    /api/workflows                 -> list all workflows
POST   /api/workflows                 -> create a workflow
GET    /api/workflows/:id             -> get one workflow
PATCH  /api/workflows/:id             -> update a workflow
DELETE /api/workflows/:id             -> delete a workflow
POST   /api/workflows/:id/publish     -> publish a draft workflow
GET    /api/workflows/:id/runs        -> view recent run history
"""
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends
from bson import ObjectId

from db import workflows_col, workflow_runs_col
from models import WorkflowCreate, WorkflowUpdate
from auth import require_staff

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


def serialize(workflow: dict) -> dict:
    workflow["id"] = str(workflow.pop("_id"))
    return workflow


@router.get("")
async def list_workflows(user: dict = Depends(require_staff)):
    cursor = workflows_col.find({}).sort("createdAt", -1)
    workflows = await cursor.to_list(length=200)
    return {"workflows": [serialize(w) for w in workflows]}


@router.post("")
async def create_workflow(payload: WorkflowCreate, user: dict = Depends(require_staff)):
    doc = payload.model_dump()
    doc["status"] = "draft"
    doc["createdAt"] = datetime.now(timezone.utc)
    doc["updatedAt"] = datetime.now(timezone.utc)
    result = await workflows_col.insert_one(doc)
    doc["_id"] = result.inserted_id
    return serialize(doc)


@router.get("/{workflow_id}")
async def get_workflow(workflow_id: str, user: dict = Depends(require_staff)):
    if not ObjectId.is_valid(workflow_id):
        raise HTTPException(status_code=400, detail="Invalid workflow ID")
    workflow = await workflows_col.find_one({"_id": ObjectId(workflow_id)})
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return serialize(workflow)


@router.patch("/{workflow_id}")
async def update_workflow(workflow_id: str, payload: WorkflowUpdate, user: dict = Depends(require_staff)):
    if not ObjectId.is_valid(workflow_id):
        raise HTTPException(status_code=400, detail="Invalid workflow ID")
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    updates["updatedAt"] = datetime.now(timezone.utc)
    result = await workflows_col.find_one_and_update(
        {"_id": ObjectId(workflow_id)}, {"$set": updates}, return_document=True
    )
    if not result:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return serialize(result)


@router.delete("/{workflow_id}")
async def delete_workflow(workflow_id: str, user: dict = Depends(require_staff)):
    if not ObjectId.is_valid(workflow_id):
        raise HTTPException(status_code=400, detail="Invalid workflow ID")
    result = await workflows_col.delete_one({"_id": ObjectId(workflow_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return {"deleted": True}


@router.post("/{workflow_id}/publish")
async def publish_workflow(workflow_id: str, user: dict = Depends(require_staff)):
    if not ObjectId.is_valid(workflow_id):
        raise HTTPException(status_code=400, detail="Invalid workflow ID")
    result = await workflows_col.find_one_and_update(
        {"_id": ObjectId(workflow_id)},
        {"$set": {"status": "published", "updatedAt": datetime.now(timezone.utc)}},
        return_document=True,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return serialize(result)


@router.get("/{workflow_id}/runs")
async def get_workflow_runs(workflow_id: str, user: dict = Depends(require_staff)):
    cursor = workflow_runs_col.find({"workflowId": workflow_id}).sort("startedAt", -1)
    runs = await cursor.to_list(length=20)
    for run in runs:
        run["id"] = str(run.pop("_id"))
    return {"runs": runs}
