"""
Vendor SLA acceptance + escalation — the specific gap named directly in
current (2026) market analysis of AppFolio/Buildium: neither platform
tracks whether a dispatched vendor actually accepted a job, or
escalates automatically if the vendor goes silent. A work order in
either competitor is "assigned" the moment staff (or their own
auto-dispatch) picks a vendor — there's no confirmation loop and no
fallback if that vendor never shows up.

Real flow this module supports:
1. A vendor is dispatched (auto or manual assignment) -> this module
   generates a real, single-use acceptance token, sets a real SLA
   deadline, and sends a real SMS with a public accept link (no login
   required — vendors have no account in this app).
2. The vendor taps the link -> routers/vendor_acceptance.py's public
   endpoint marks the ticket accepted.
3. If the deadline passes with no acceptance, the scheduled check
   (_do_vendor_sla_check in routers/admin.py) tries the NEXT vendor in
   that property's preferredVendors list for the ticket's category
   (see models.py's PreferredVendorsUpdate), skipping the one that
   didn't respond — or, if no further vendor is configured, escalates
   directly to staff with a clear, honest "nobody has confirmed this
   yet" notification, rather than a ticket silently sitting assigned
   to a vendor who may never show up.

Vendors have no login in this app (confirmed elsewhere in this
codebase) — acceptance is a public, tokenized link, not an
authenticated action. The token is a real secrets.token_urlsafe value,
single-use (cleared once accepted), and time-bounded (expires with the
SLA window itself — an old, expired link can't retroactively "accept"
a job that's already been reassigned).
"""
import os
import secrets
from datetime import datetime, timezone, timedelta

from db import tickets_col, properties_col, vendors_col
import notifications_service
import sms_service
from sms_service import SmsNotConfigured, SmsSendError

PUBLIC_BASE_URL = "https://rentflow-ai.onrender.com"
DEFAULT_SLA_HOURS = 2  # matches the "2 hours" figure named directly in the market research this feature is built against


def normalize_preferred_vendor_ids(raw_value) -> list[str]:
    """Reads a property's preferredVendors[category] value defensively —
    a plain string (data written under the earlier single-vendor
    version of this feature, deployed earlier the same day this
    changed) is normalized to a one-item list; a real list passes
    through unchanged; anything else (missing, None) becomes an empty
    list. No migration needed for whatever staff already configured."""
    if not raw_value:
        return []
    if isinstance(raw_value, str):
        return [raw_value]
    if isinstance(raw_value, list):
        return [v for v in raw_value if v]
    return []


async def find_next_eligible_vendor(property_id: str, category: str, exclude_vendor_ids: list[str] | None = None) -> dict | None:
    """Same real eligibility gate as the original find_preferred_vendor
    (active, insurance/license not expired) — now also skips any
    vendor id in exclude_vendor_ids, which is what makes real SLA
    fallback possible: try vendor #1, and if they don't accept in
    time, this same function call (with vendor #1's id excluded)
    finds vendor #2 instead, without duplicating the eligibility
    logic."""
    from bson import ObjectId
    exclude_vendor_ids = set(exclude_vendor_ids or [])

    query_id = ObjectId(property_id) if property_id and ObjectId.is_valid(property_id) else property_id
    property_doc = await properties_col.find_one({"_id": query_id})
    if not property_doc:
        return None

    candidate_ids = normalize_preferred_vendor_ids(property_doc.get("preferredVendors", {}).get(category))
    now = datetime.now(timezone.utc)
    property_org_id = property_doc.get("orgId")

    for vendor_id in candidate_ids:
        if vendor_id in exclude_vendor_ids or not ObjectId.is_valid(vendor_id):
            continue
        vendor = await vendors_col.find_one({"_id": ObjectId(vendor_id)})
        if not vendor or not vendor.get("active", True):
            continue
        # Defense in depth: a vendor referenced in preferredVendors
        # should always already belong to the same org as the property
        # (vendors.py only ever lets staff choose from their own org's
        # roster), but this real check makes that a guarantee rather
        # than an assumption - stale data or a future bug elsewhere
        # can never cause a property in one organization to auto-
        # dispatch a vendor belonging to a different one.
        if property_org_id and vendor.get("orgId") != property_org_id:
            continue
        expired = False
        for field in ("insuranceExpiresDate", "licenseExpiresDate"):
            expires = vendor.get(field)
            if isinstance(expires, datetime):
                if expires.tzinfo is None:
                    expires = expires.replace(tzinfo=timezone.utc)
                if expires <= now:
                    expired = True
                    break
        if expired:
            continue
        return vendor

    return None


async def dispatch_with_sla(ticket_id: str, ticket: dict, vendor: dict, sla_hours: int = DEFAULT_SLA_HOURS) -> dict:
    """Real, shared dispatch logic used by BOTH auto-assignment
    (routers/maintenance.py's create_ticket) and manual staff
    assignment (routers/vendors.py's assign_vendor_to_ticket) — one
    code path, so a manually-assigned vendor gets the exact same real
    acceptance tracking an auto-assigned one does, not a second,
    parallel implementation that could drift.

    Sends a real SMS if the vendor has a phone on file; if not,
    reports that honestly in the returned dict rather than silently
    skipping tracking altogether — the ticket still gets a real
    deadline and escalates on schedule even if the vendor can't be
    reached this way, since staff should know their vendor has no
    confirmed way to receive dispatches."""
    token = secrets.token_urlsafe(24)
    now = datetime.now(timezone.utc)
    deadline = now + timedelta(hours=sla_hours)

    updates = {
        "assignedVendorId": str(vendor["_id"]),
        "assignedVendorName": vendor["name"],
        "estimatedCost": vendor.get("baseCost"),
        "estimatedArrivalHours": vendor.get("avgArrivalHours"),
        "status": "in_progress",
        "vendorAcceptanceStatus": "pending",
        "vendorAcceptanceToken": token,
        "vendorAcceptanceDeadline": deadline,
        "vendorAssignedAt": now,
        "vendorDeclinedIds": ticket.get("vendorDeclinedIds", []),  # preserved across reassignment attempts
        "updatedAt": now,
    }
    await tickets_col.update_one({"_id": ticket["_id"]}, {"$set": updates})

    sms_result = {"attempted": False, "sent": False, "note": ""}
    vendor_phone = vendor.get("phone")
    if vendor_phone:
        accept_url = f"{PUBLIC_BASE_URL}/api/vendor-acceptance/{token}"
        body = (
            f"PropWise AI: You've been assigned to a job — {ticket.get('title', 'maintenance request')} "
            f"at Unit {ticket.get('unitId', '?')}. Please confirm within {sla_hours}h: {accept_url}"
        )
        sms_result["attempted"] = True
        try:
            await sms_service.send_sms_async(vendor_phone, body)
            sms_result["sent"] = True
        except (SmsNotConfigured, SmsSendError) as exc:
            sms_result["note"] = str(exc)
    else:
        sms_result["note"] = "Vendor has no phone number on file — SLA tracking started, but no confirmation SMS could be sent."

    return {"token": token, "deadline": deadline, "sms": sms_result}
