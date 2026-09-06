"""
Tenant documents & e-signature. Staff create a document (e.g. a lease
addendum) attached to a specific lease; the named tenant can view, e-sign
(typed name + timestamp, not a legally-binding digital signature service —
see note below), and download it as a PDF.

IMPORTANT: any "content" text stored here is whatever staff provide when
creating the document. This app does not generate legal language — lease
and agreement wording should come from a real estate attorney or a
licensed template provider before being used with real tenants.

BUG FIX (Sept 3, 2026): documents had no building name anywhere - not in
the PDF, not in the in-app list, not even a raw propertyId to fall back
on, since a document only ever stored leaseId, never propertyId directly.
Confirmed the frontend create form never even collected leaseId at all,
so most real documents had nothing to resolve a building name FROM in the
first place - see Documents.jsx's own new lease-picker for the other half
of this fix. Resolved live (via leaseId -> lease -> property), not stored
as a snapshot at creation time, so a later property rename is reflected
correctly rather than needing every existing document backfilled.

MULTI-TENANCY: every document carries a real orgId, stamped server-side
at creation from the creating staff member's own orgId - never client-
submitted. Every query below is scoped by orgId, alongside the existing
tenantEmail ownership check for resident-facing endpoints (defense in
depth - the two checks can never disagree in practice, but neither
alone is redundant to keep).
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

from db import documents_col, leases_col, properties_col
from models import DocumentCreate, DocumentSign
from auth import require_staff, get_current_user

router = APIRouter(prefix="/api/documents", tags=["documents"])


def _pdf_text(value) -> str:
    return _xml_escape(str(value) if value is not None else "")


async def _resolve_building_name(lease_id: str | None) -> str | None:
    """Real, live resolution: leaseId -> lease's propertyId -> property's
    name. Returns None (not a placeholder string) at any step that
    doesn't resolve - a document genuinely not tied to a lease yet is a
    real, valid state (see DocumentCreate's leaseId being Optional),
    not an error to paper over with a fake value."""
    if not lease_id or not ObjectId.is_valid(lease_id):
        return None
    lease = await leases_col.find_one({"_id": ObjectId(lease_id)})
    if not lease:
        return None
    property_id = lease.get("propertyId")
    if not property_id:
        return None
    query_id = ObjectId(property_id) if ObjectId.is_valid(property_id) else property_id
    property_doc = await properties_col.find_one({"_id": query_id})
    return property_doc.get("name") if property_doc else None


@router.post("")
async def create_document(payload: DocumentCreate, user: dict = Depends(require_staff)):
    doc = payload.model_dump()
    doc["orgId"] = user["orgId"]
    doc["status"] = "pending"
    doc["signedByName"] = None
    doc["signedAt"] = None
    doc["createdAt"] = datetime.now(timezone.utc)
    result = await documents_col.insert_one(doc)
    return {"documentId": str(result.inserted_id)}


@router.get("")
async def list_documents(user: dict = Depends(get_current_user)):
    query = {"orgId": user.get("orgId")}
    if user["role"] != "staff":
        query["tenantEmail"] = user["email"]
    cursor = documents_col.find(query).sort("createdAt", -1).limit(200)
    results = await cursor.to_list(length=200)
    for r in results:
        r["_id"] = str(r["_id"])
        r["buildingName"] = await _resolve_building_name(r.get("leaseId"))
    return {"documents": results}


@router.get("/{document_id}")
async def get_document(document_id: str, user: dict = Depends(get_current_user)):
    if not ObjectId.is_valid(document_id):
        raise HTTPException(status_code=400, detail="Invalid document ID")
    doc = await documents_col.find_one({"_id": ObjectId(document_id), "orgId": user.get("orgId")})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if user["role"] != "staff" and doc.get("tenantEmail") != user["email"]:
        raise HTTPException(status_code=403, detail="Not your document")
    doc["_id"] = str(doc["_id"])
    doc["buildingName"] = await _resolve_building_name(doc.get("leaseId"))
    return doc


@router.post("/{document_id}/sign")
async def sign_document(document_id: str, payload: DocumentSign, user: dict = Depends(get_current_user)):
    if not ObjectId.is_valid(document_id):
        raise HTTPException(status_code=400, detail="Invalid document ID")
    doc = await documents_col.find_one({"_id": ObjectId(document_id), "orgId": user.get("orgId")})
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

    # This is the actual self-service renewal effect - signing a
    # renewal document (documentType='renewal', set only by
    # leases.py's request_lease_renewal) genuinely extends the real
    # lease record right here, no staff action needed. A signed
    # INITIAL lease document does NOT hit this branch at all -
    # documentType defaults to 'lease' for those, so nothing about the
    # existing initial-lease signing flow changes.
    if doc.get("documentType") == "renewal" and doc.get("leaseId") and doc.get("proposedEndDate"):
        await leases_col.update_one(
            {"_id": ObjectId(doc["leaseId"])},
            {"$set": {"endDate": doc["proposedEndDate"], "renewalStatus": "signed"}},
        )

    return {"status": "signed"}


@router.get("/{document_id}/pdf")
async def document_pdf(document_id: str, user: dict = Depends(get_current_user)):
    if not ObjectId.is_valid(document_id):
        raise HTTPException(status_code=400, detail="Invalid document ID")
    doc = await documents_col.find_one({"_id": ObjectId(document_id), "orgId": user.get("orgId")})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if user["role"] != "staff" and doc.get("tenantEmail") != user["email"]:
        raise HTTPException(status_code=403, detail="Not your document")

    building_name = await _resolve_building_name(doc.get("leaseId"))

    buffer = BytesIO()
    pdf = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.8 * inch, bottomMargin=0.8 * inch)
    styles = getSampleStyleSheet()
    building_style = ParagraphStyle("Building", parent=styles["Normal"], fontSize=12, textColor="#1e293b", spaceAfter=2)
    title_style = ParagraphStyle("TitleCustom", parent=styles["Title"], fontSize=16, spaceAfter=10)
    body_style = ParagraphStyle("Body", parent=styles["Normal"], fontSize=10, leading=15, spaceAfter=8)
    sig_style = ParagraphStyle("Sig", parent=styles["Normal"], fontSize=10, textColor="#334155", spaceBefore=20)

    story = []
    # Real letterhead - the actual gap this fix addresses. Omitted
    # entirely (not a placeholder like "Unknown building") when this
    # document genuinely has no resolvable lease/property, which is
    # an honest state for a document created before a lease was
    # selected, or one never tied to a specific unit at all.
    if building_name:
        story.append(Paragraph(_pdf_text(building_name), building_style))
    story.append(Paragraph(_pdf_text(doc.get("title")), title_style))
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
