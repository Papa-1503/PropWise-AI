"""
Public vendor acceptance endpoint — a vendor taps the link sent by SMS
(see vendor_sla_service.py) and this confirms their job assignment,
with zero login required. Vendors have no account in this app; a
tokenized link is the real, honest mechanism for this, not a fake
login wall.

GET /api/vendor-acceptance/{token} -> confirms acceptance, returns a
plain, self-contained HTML confirmation page (a vendor clicking this
from a phone's SMS app should see something readable immediately, not
JSON).
"""
from datetime import datetime, timezone

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from db import tickets_col
from audit_service import log_action

router = APIRouter(prefix="/api/vendor-acceptance", tags=["vendor-acceptance"])


def _page(title: str, message: str) -> str:
    """Small, self-contained HTML page — no frontend build/routing
    involved, since this is meant to be opened directly from an SMS
    link on a vendor's phone, not navigated to inside the React app."""
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{title}</title>
<style>
  body {{ font-family: -apple-system, sans-serif; background: #f6f3ec; margin: 0; padding: 40px 20px;
         display: flex; align-items: center; justify-content: center; min-height: 100vh; }}
  .card {{ background: white; border-radius: 16px; padding: 32px 28px; max-width: 420px;
           box-shadow: 0 4px 20px rgba(0,0,0,0.08); text-align: center; }}
  h1 {{ font-size: 20px; color: #14213d; margin: 0 0 12px; }}
  p {{ font-size: 15px; color: #475569; line-height: 1.5; margin: 0; }}
</style>
</head>
<body>
  <div class="card">
    <h1>{title}</h1>
    <p>{message}</p>
  </div>
</body>
</html>"""


@router.get("/{token}", response_class=HTMLResponse)
async def accept_vendor_dispatch(token: str):
    ticket = await tickets_col.find_one({"vendorAcceptanceToken": token})
    if not ticket:
        return _page("Link not found", "This confirmation link isn't valid — it may have already been used, or the job may have been reassigned to someone else.")

    if ticket.get("vendorAcceptanceStatus") == "accepted":
        return _page("Already confirmed", "This job was already confirmed. No further action needed.")

    deadline = ticket.get("vendorAcceptanceDeadline")
    now = datetime.now(timezone.utc)
    if isinstance(deadline, datetime):
        deadline_aware = deadline.replace(tzinfo=timezone.utc) if deadline.tzinfo is None else deadline
        if deadline_aware <= now:
            return _page("Link expired", "This confirmation window has passed and the job may have already been reassigned. Please contact the property office directly.")

    await tickets_col.update_one(
        {"_id": ticket["_id"]},
        {"$set": {"vendorAcceptanceStatus": "accepted", "vendorAcceptedAt": now}},
    )

    await log_action(
        actor_id="vendor_public_link", actor_email="",
        action="vendor_accepted_dispatch", target_type="ticket", target_id=str(ticket["_id"]),
        details={"vendorId": ticket.get("assignedVendorId"), "vendorName": ticket.get("assignedVendorName")},
    )

    return _page(
        "Confirmed ✓",
        f"You're confirmed for: {ticket.get('title', 'this job')} at Unit {ticket.get('unitId', '')}. "
        f"The property team has been notified.",
    )
