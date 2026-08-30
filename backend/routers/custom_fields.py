"""
Custom fields (P18).

POST /api/custom-fields/definitions              -> define a new field for an entity type
GET  /api/custom-fields/definitions?entityType=   -> list defined fields
POST /api/custom-fields/{entityType}/{entityId}   -> set a real value, validated
                                                      against the field's defined type
GET  /api/custom-fields/{entityType}/{entityId}   -> get all custom field values for
                                                      one real entity

Deliberately stores values in their own collection
(custom_field_values), keyed by (entityType, entityId, fieldName),
rather than embedding them directly into units/leases/vendors/tickets.
This means zero existing write paths in this app need to change to
support custom fields - leases.py, properties.py, etc. keep writing
exactly what they already write, and this is purely additive data
alongside it. The tradeoff, stated honestly: reading an entity's
custom fields is a second query, not embedded in the same document -
a real cost, but a much smaller one than touching every existing
create/update endpoint across 4 different routers.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends

from db import custom_field_definitions_col, custom_field_values_col
from models import CustomFieldDefinitionCreate, CustomFieldValueSet
from auth import require_staff

router = APIRouter(prefix="/api/custom-fields", tags=["custom-fields"])


def serialize(doc: dict) -> dict:
    doc = dict(doc)
    doc["id"] = str(doc.pop("_id"))
    return doc


@router.post("/definitions")
async def create_field_definition(payload: CustomFieldDefinitionCreate, user: dict = Depends(require_staff)):
    existing = await custom_field_definitions_col.find_one({
        "entityType": payload.entityType, "fieldName": payload.fieldName,
    })
    if existing:
        raise HTTPException(status_code=409, detail=f"A field named '{payload.fieldName}' already exists for {payload.entityType}.")

    doc = payload.model_dump()
    doc["createdAt"] = datetime.now(timezone.utc)
    result = await custom_field_definitions_col.insert_one(doc)
    doc["_id"] = result.inserted_id
    return serialize(doc)


@router.get("/definitions")
async def list_field_definitions(entityType: str | None = None, user: dict = Depends(require_staff)):
    query = {"entityType": entityType} if entityType else {}
    defs = await custom_field_definitions_col.find(query).sort("fieldName", 1).to_list(length=200)
    return {"definitions": [serialize(d) for d in defs]}


def _validate_value(field_type: str, value) -> None:
    if value is None:
        return
    if field_type == "number" and not isinstance(value, (int, float)):
        raise HTTPException(status_code=400, detail=f"Expected a number for this field, got {type(value).__name__}.")
    if field_type == "boolean" and not isinstance(value, bool):
        raise HTTPException(status_code=400, detail=f"Expected true/false for this field, got {type(value).__name__}.")
    if field_type in ("text", "date") and not isinstance(value, str):
        raise HTTPException(status_code=400, detail=f"Expected text for this field, got {type(value).__name__}.")


@router.post("/{entity_type}/{entity_id}")
async def set_field_value(entity_type: str, entity_id: str, payload: CustomFieldValueSet, user: dict = Depends(require_staff)):
    field_def = await custom_field_definitions_col.find_one({"entityType": entity_type, "fieldName": payload.fieldName})
    if not field_def:
        raise HTTPException(status_code=404, detail=f"No custom field named '{payload.fieldName}' is defined for {entity_type}.")

    _validate_value(field_def["fieldType"], payload.value)
    if field_def.get("required") and payload.value is None:
        raise HTTPException(status_code=400, detail=f"'{payload.fieldName}' is required and cannot be cleared.")

    await custom_field_values_col.update_one(
        {"entityType": entity_type, "entityId": entity_id, "fieldName": payload.fieldName},
        {"$set": {"value": payload.value, "updatedAt": datetime.now(timezone.utc)}},
        upsert=True,
    )
    return {"entityType": entity_type, "entityId": entity_id, "fieldName": payload.fieldName, "value": payload.value}


@router.get("/{entity_type}/{entity_id}")
async def get_entity_field_values(entity_type: str, entity_id: str, user: dict = Depends(require_staff)):
    values = await custom_field_values_col.find({"entityType": entity_type, "entityId": entity_id}).to_list(length=200)
    return {"values": {v["fieldName"]: v["value"] for v in values}}
