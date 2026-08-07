"""
Tenant documents & e-signature. Staff create a document (e.g. a lease
addendum) attached to a specific lease; the named tenant can view, e-sign
(typed name + timestamp, not a legally-binding digital signature service —
see note below), and download it as a PDF.

IMPORTANT: any "content" text stored here is whatever staff provide when
creating the document. This app does not generate legal language — lease
and agreement wording should come from a real estate attorney or a
licensed template provider before being used with real tenants.
"""
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from bson import ObjectId
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from xml.sax.saxutils import escape as _xml_escape

from db import documents_col
from models import DocumentCreate, DocumentSign
from auth import require_staff, get_current_user

router = APIRouter(prefix="/api/documents", tags=["documents"])


def _pdf_text(value) -> str:
    return _xml_escape(str(value) if value is not None else "")


@router.post("")
async def create_document(payload: DocumentCreate, user: dict = Depends(require_staff)):
    doc = payload.model_dump()
    doc["status"] = "pending"
    doc["signedByName"] = None
    doc["signedAt"] = None
    doc["createdAt"] = datetime.now(timezone.utc)
    result = await documents_col.insert_one(doc)
    return {"documentId": str(result.inserted_id)}


@router.get("")
async def list_documents(user: dict = Depends(get_current_user)):
    query = {} if user["role"] == "staff" else {"tenantEmail": user["email"]}
    cursor = documents_col.find(query).sort("createdAt", -1).limit(200)
    results = await cursor.to_list(length=200)
    for r in results:
        r["_id"] = str(r["_id"])
    return {"documents": results}


@router.get("/{document_id}")
async def get_document(document_id: str, user: dict = Depends(get_current_user)):
    if not ObjectId.is_valid(document_id):
        raise HTTPException(status_code=400, detail="Invalid document ID")
    doc = await documents_col.find_one({"_id": ObjectId(document_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if user["role"] != "staff" and doc.get("tenantEmail") != user["email"]:
        raise HTTPException(status_code=403, detail="Not your document")
    doc["_id"] = str(doc["_id"])
    return doc


@router.post("/{document_id}/sign")
async def sign_document(document_id: str, payload: DocumentSign, user: dict = Depends(get_current_user)):
    if not ObjectId.is_valid(document_id):
        raise HTTPException(status_code=400, detail="Invalid document ID")
    doc = await documents_col.find_one({"_id": ObjectId(document_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if doc.get("tenantEmail") != user["email"]:
        raise HTTPException(status_code=403, detail="Only the named tenant can sign this document")
    if doc.get("status") == "signed":
        raise HTTPException(status_code=400, detail="Already signed")

    await documents_col.update_one(
        {"_id": ObjectId(document_id)},
        {"$set": {"status": "signed", "signedByName": payload.signedByName, "signedAt": datetime.now(timezone.utc)}},
    )
    return {"status": "signed"}


@router.get("/{document_id}/pdf")
async def document_pdf(document_id: str, user: dict = Depends(get_current_user)):
    if not ObjectId.is_valid(document_id):
        raise HTTPException(status_code=400, detail="Invalid document ID")
    doc = await documents_col.find_one({"_id": ObjectId(document_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if user["role"] != "staff" and doc.get("tenantEmail") != user["email"]:
        raise HTTPException(status_code=403, detail="Not your document")

    buffer = BytesIO()
    pdf = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.8 * inch, bottomMargin=0.8 * inch)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("TitleCustom", parent=styles["Title"], fontSize=16, spaceAfter=10)
    body_style = ParagraphStyle("Body", parent=styles["Normal"], fontSize=10, leading=15, spaceAfter=8)
    sig_style = ParagraphStyle("Sig", parent=styles["Normal"], fontSize=10, textColor="#334155", spaceBefore=20)

    story = [Paragraph(_pdf_text(doc.get("title")), title_style)]
    for para in str(doc.get("content", "")).split("\n\n"):
        if para.strip():
            story.append(Paragraph(_pdf_text(para), body_style))
    story.append(Spacer(1, 0.3 * inch))
    if doc.get("status") == "signed":
        signed_at = doc.get("signedAt")
        story.append(Paragraph(
            f"Signed by: {_pdf_text(doc.get('signedByName'))} on "
            f"{signed_at.strftime('%B %d, %Y at %I:%M %p UTC') if signed_at else 'unknown date'}",
            sig_style,
        ))
    else:
        story.append(Paragraph("Not yet signed.", sig_style))

    pdf.build(story)
    buffer.seek(0)
    filename = f"document_{document_id[-6:]}.pdf"
    return StreamingResponse(
        buffer, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
