"""
Customer data export — a real, genuinely missing piece before this.
If a customer ever wants to leave, or simply wants their own data for
their own records, there was no built-in way to get it out except
asking staff to manually query the database. For a product handling
real leases, payments, and resident PII, this matters both for trust
(a real answer to "can I get my data out?") and because a Data
Processing Addendum commonly promises this capability.

GET /api/organizations/me/export -> (org owner only) a single
                                     downloadable JSON file containing
                                     every real business-data document
                                     that belongs to this organization

Deliberately excludes a real, specific set of collections that are
NOT this organization's own business data, even though they carry an
orgId field: password_reset_tokens (transient security tokens, already
single-use and short-lived - exporting them would just be an expired
token, never a real credential), photo_upload_tokens (same - transient
access tokens, not content), and scheduler_health (this app's own
internal operational telemetry, not anything the organization created
or owns). Every other org-scoped collection is included - see
COLLECTIONS_TO_EXPORT below for the full, real list.

Uses the exact same bson.json_util serialization as scripts/backup_db.py
so ObjectIds, datetimes, and other real BSON types round-trip
correctly in the downloaded file, not just python's stdlib json (which
cannot represent these types at all).
"""
import io
from datetime import datetime, timezone

from bson import json_util, ObjectId
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse

from db import (
    organizations_col, users_col, properties_col, leases_col, tickets_col,
    vendors_col, vendor_bids_col, payments_col, notifications_col,
    market_rent_analyses_col, tour_slots_col, tour_bookings_col,
    smart_lock_access_log_col, accounting_connections_col, renewal_checkins_col,
    posts_col, leads_col, documents_col, gallery_photos_col, screening_col,
    bank_lines_col, workflows_col, workflow_runs_col, maintenance_schedules_col,
    communications_col, on_call_shifts_col, on_call_log_col, voice_triage_col,
    sms_triage_col, audit_log_col, budgets_col, kb_articles_col, supplies_col,
    supply_orders_col, repair_items_col, labor_rates_col, fixed_assets_col,
    capital_projects_col, custom_field_definitions_col, custom_field_values_col,
    communication_templates_col, custom_roles_col, custom_views_col,
    custom_reports_col, application_questions_col, packages_col,
    community_posts_col, late_notices_col, inspections_col, photos_col,
    unit_baseline_photos_col, condition_reports_col,
)
from auth import get_current_user

router = APIRouter(prefix="/api/organizations/me", tags=["organizations"])

# Every real, org-owned business-data collection this app has - see
# this module's own docstring for the 3 deliberately excluded ones
# (transient security tokens and internal system telemetry, not
# anything the organization itself created).
COLLECTIONS_TO_EXPORT = {
    "properties": properties_col,
    "leases": leases_col,
    "maintenanceTickets": tickets_col,
    "inspections": inspections_col,
    "inspectionPhotos": photos_col,
    "unitBaselinePhotos": unit_baseline_photos_col,
    "conditionReports": condition_reports_col,
    "vendors": vendors_col,
    "vendorBids": vendor_bids_col,
    "payments": payments_col,
    "notifications": notifications_col,
    "marketRentAnalyses": market_rent_analyses_col,
    "tourSlots": tour_slots_col,
    "tourBookings": tour_bookings_col,
    "smartLockAccessLog": smart_lock_access_log_col,
    "accountingConnections": accounting_connections_col,
    "renewalCheckins": renewal_checkins_col,
    "staffPosts": posts_col,
    "leads": leads_col,
    "documents": documents_col,
    "galleryPhotos": gallery_photos_col,
    "screeningRequests": screening_col,
    "bankStatementLines": bank_lines_col,
    "workflows": workflows_col,
    "workflowRuns": workflow_runs_col,
    "maintenanceSchedules": maintenance_schedules_col,
    "communications": communications_col,
    "onCallShifts": on_call_shifts_col,
    "onCallLog": on_call_log_col,
    "voiceTriage": voice_triage_col,
    "smsTriage": sms_triage_col,
    "auditLog": audit_log_col,
    "budgets": budgets_col,
    "kbArticles": kb_articles_col,
    "supplies": supplies_col,
    "supplyOrders": supply_orders_col,
    "repairItems": repair_items_col,
    "laborRates": labor_rates_col,
    "fixedAssets": fixed_assets_col,
    "capitalProjects": capital_projects_col,
    "customFieldDefinitions": custom_field_definitions_col,
    "customFieldValues": custom_field_values_col,
    "communicationTemplates": communication_templates_col,
    "customRoles": custom_roles_col,
    "customViews": custom_views_col,
    "customReports": custom_reports_col,
    "applicationQuestions": application_questions_col,
    "packages": packages_col,
    "communityPosts": community_posts_col,
    "lateNotices": late_notices_col,
}


async def _require_org_owner_for_export(user: dict = Depends(get_current_user)) -> dict:
    """Same real ownership boundary as routers/billing.py's
    _require_org_owner - exporting the organization's ENTIRE dataset
    is at least as sensitive as changing its billing, so it's gated
    the same way, not opened up to every staff member."""
    if user.get("role") != "staff" or not user.get("isOrgOwner"):
        raise HTTPException(status_code=403, detail="Only the organization owner can export the organization's data.")
    return user


@router.get("/export")
async def export_organization_data(user: dict = Depends(_require_org_owner_for_export)):
    org_id = user["orgId"]
    query_id = ObjectId(org_id) if ObjectId.is_valid(org_id) else org_id

    org_doc = await organizations_col.find_one({"_id": query_id})
    if not org_doc:
        raise HTTPException(status_code=404, detail="Organization not found")

    export = {
        "exportedAt": datetime.now(timezone.utc).isoformat(),
        "organization": org_doc,
        "users": await users_col.find({"orgId": org_id}).to_list(length=10000),
    }

    for key, collection in COLLECTIONS_TO_EXPORT.items():
        export[key] = await collection.find({"orgId": org_id}).to_list(length=50000)

    # json_util.dumps (not plain json.dumps) is what correctly
    # preserves ObjectId, datetime, and other real BSON types as a
    # real, re-importable representation - same reasoning as
    # scripts/backup_db.py's own use of it.
    payload = json_util.dumps(export, indent=2)
    buffer = io.BytesIO(payload.encode("utf-8"))

    org_name_safe = (org_doc.get("name") or "organization").replace(" ", "_")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"propwise_export_{org_name_safe}_{timestamp}.json"

    return StreamingResponse(
        buffer, media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
