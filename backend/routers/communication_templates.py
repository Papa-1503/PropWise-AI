"""
Customized communication templates (P18).

GET/POST   /api/communication-templates                  -> template CRUD
PATCH      /api/communication-templates/{id}
DELETE     /api/communication-templates/{id}
POST       /api/communication-templates/{id}/render       -> real variable
                                                              substitution
                                                              against a lease

Placeholders use {{fieldName}} syntax. Rendered directly against a
real lease document's actual fields (residentName, unitId, rent,
startDate, endDate, renewalStatus) - never a separate, hand-maintained
merge-field list that could drift from what a lease record actually
contains. An unrecognized placeholder is left in the output as-is
(e.g. literal "{{notARealField}}") rather than silently deleted or
raising an error - visible and obviously wrong if someone made a typo,
which is more useful than either extreme.
"""
import re
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends
from bson import ObjectId

from db import communication_templates_col, leases_col
from models import CommunicationTemplateCreate, CommunicationTemplateUpdate
from auth import require_staff

router = APIRouter(prefix="/api/communication-templates", tags=["communication-templates"])


def serialize(doc: dict) -> dict:
    doc = dict(doc)
    doc["id"] = str(doc.pop("_id"))
    return doc


def _render(text: str, lease: dict) -> str:
    def replace(match):
        field_name = match.group(1)
        value = lease.get(field_name)
        if value is None:
            return match.group(0)
        if isinstance(value, datetime):
            return value.strftime("%B %d, %Y")
        return str(value)

    return re.sub(r"\{\{(\w+)\}\}", replace, text)


@router.post("")
async def create_template(payload: CommunicationTemplateCreate, user: dict = Depends(require_staff)):
    doc = payload.model_dump()
    doc["createdAt"] = datetime.now(timezone.utc)
    result = await communication_templates_col.insert_one(doc)
    doc["_id"] = result.inserted_id
    return serialize(doc)


@router.get("")
async def list_templates(channel: str | None = None, user: dict = Depends(require_staff)):
    query = {"channel": channel} if channel else {}
    templates = await communication_templates_col.find(query).sort("name", 1).to_list(length=200)
    return {"templates": [serialize(t) for t in templates]}


@router.patch("/{template_id}")
async def update_template(template_id: str, payload: CommunicationTemplateUpdate, user: dict = Depends(require_staff)):
    if not ObjectId.is_valid(template_id):
        raise HTTPException(status_code=400, detail="Invalid template ID")
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    result = await communication_templates_col.find_one_and_update(
        {"_id": ObjectId(template_id)}, {"$set": updates}, return_document=True
    )
    if not result:
        raise HTTPException(status_code=404, detail="Template not found")
    return serialize(result)


@router.delete("/{template_id}")
async def delete_template(template_id: str, user: dict = Depends(require_staff)):
    if not ObjectId.is_valid(template_id):
        raise HTTPException(status_code=400, detail="Invalid template ID")
    result = await communication_templates_col.delete_one({"_id": ObjectId(template_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Template not found")
    return {"deleted": True}


@router.post("/{template_id}/render")
async def render_template(template_id: str, leaseId: str, user: dict = Depends(require_staff)):
    if not ObjectId.is_valid(template_id):
        raise HTTPException(status_code=400, detail="Invalid template ID")
    template = await communication_templates_col.find_one({"_id": ObjectId(template_id)})
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    if not ObjectId.is_valid(leaseId):
        raise HTTPException(status_code=400, detail="Invalid lease ID")
    lease = await leases_col.find_one({"_id": ObjectId(leaseId)})
    if not lease:
        raise HTTPException(status_code=404, detail="Lease not found")

    rendered_body = _render(template["body"], lease)
    rendered_subject = _render(template["subject"], lease) if template.get("subject") else None

    return {
        "channel": template["channel"],
        "subject": rendered_subject,
        "body": rendered_body,
        "to": lease.get("residentEmail") if template["channel"] == "email" else lease.get("residentPhone"),
    }
