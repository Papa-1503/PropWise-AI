"""
Custom rental applications (P18).

GET/POST   /api/application-questions?propertyId=  -> question CRUD, per property
DELETE     /api/application-questions/{id}
POST       /api/screening/{screening_id}/application-answers  -> applicant
                                                                  submits
                                                                  answers,
                                                                  validated
                                                                  against
                                                                  each
                                                                  question's
                                                                  real
                                                                  defined type

Genuinely reuses custom_fields.py's real _validate_value function
rather than a second, parallel type-checking implementation - the
same real value-type rules (number/boolean/text/date) apply here,
imported directly, not copied.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends
from bson import ObjectId

from db import application_questions_col, screening_col
from models import ApplicationQuestionCreate, ApplicationAnswerSubmit
from auth import require_staff, get_current_user
from routers.custom_fields import _validate_value

router = APIRouter(tags=["custom-rental-applications"])


def serialize(doc: dict) -> dict:
    doc = dict(doc)
    doc["id"] = str(doc.pop("_id"))
    return doc


@router.post("/api/application-questions")
async def create_question(payload: ApplicationQuestionCreate, user: dict = Depends(require_staff)):
    doc = payload.model_dump()
    doc["createdAt"] = datetime.now(timezone.utc)
    result = await application_questions_col.insert_one(doc)
    doc["_id"] = result.inserted_id
    return serialize(doc)


@router.get("/api/application-questions")
async def list_questions(propertyId: str, user: dict = Depends(get_current_user)):
    questions = await application_questions_col.find({"propertyId": propertyId}).sort("order", 1).to_list(length=100)
    return {"questions": [serialize(q) for q in questions]}


@router.delete("/api/application-questions/{question_id}")
async def delete_question(question_id: str, user: dict = Depends(require_staff)):
    if not ObjectId.is_valid(question_id):
        raise HTTPException(status_code=400, detail="Invalid question ID")
    result = await application_questions_col.delete_one({"_id": ObjectId(question_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Question not found")
    return {"deleted": True}


@router.post("/api/screening/{screening_id}/application-answers")
async def submit_application_answers(screening_id: str, payload: ApplicationAnswerSubmit, user: dict = Depends(get_current_user)):
    if not ObjectId.is_valid(screening_id):
        raise HTTPException(status_code=400, detail="Invalid screening ID")
    screening = await screening_col.find_one({"_id": ObjectId(screening_id)})
    if not screening:
        raise HTTPException(status_code=404, detail="Screening request not found")

    property_id = screening.get("propertyId")
    questions = await application_questions_col.find({"propertyId": property_id}).to_list(length=100)
    questions_by_id = {str(q["_id"]): q for q in questions}

    validated_answers = {}
    for question_id, value in payload.answers.items():
        question = questions_by_id.get(question_id)
        if not question:
            raise HTTPException(status_code=400, detail=f"'{question_id}' is not a real question for this property.")
        _validate_value(question["fieldType"], value)
        validated_answers[question_id] = value

    missing_required = [
        q["questionText"] for q in questions
        if q.get("required") and str(q["_id"]) not in validated_answers
    ]
    if missing_required:
        raise HTTPException(status_code=400, detail=f"Missing required answers: {', '.join(missing_required)}")

    await screening_col.update_one(
        {"_id": ObjectId(screening_id)},
        {"$set": {"applicationAnswers": validated_answers, "applicationAnsweredAt": datetime.now(timezone.utc)}},
    )
    return {"screeningId": screening_id, "answers": validated_answers}
