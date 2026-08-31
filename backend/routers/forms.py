"""
Form library (staff-facing).

GET /api/forms  -> a real, categorized catalog of every form/checklist
                    type this app actually has, so staff have one
                    place to browse rather than hunting through
                    different tabs for the right starting point.

Deliberately a real, hardcoded catalog, not a database-driven CMS -
this is fundamentally a static index of forms that already exist as
real, working features elsewhere in this app (inspections, screening,
custom rental application questions, etc.), not a new form-building
system. Each entry's realEndpoint is the actual, correct API path to
start that form - kept honest and in sync with the real routers by
hand, the same way this app's other reference lists (permission
choices, report types) are maintained.
"""
from fastapi import APIRouter, Depends

from auth import require_staff

router = APIRouter(prefix="/api/forms", tags=["forms"])

FORM_CATALOG = [
    {
        "category": "Maintenance",
        "forms": [
            {
                "name": "New maintenance ticket",
                "description": "Log a new maintenance issue for a unit.",
                "realEndpoint": "POST /api/maintenance/tickets",
            },
            {
                "name": "Unit turnover checklist - maintenance",
                "description": "The real maintenance-only view of a unit turnover checklist "
                                "(HVAC, locks, appliances, outlets, leaks) - see a turnover "
                                "inspection with ?role=maintenance.",
                "realEndpoint": "GET /api/inspections/{inspection_id}?role=maintenance",
            },
            {
                "name": "Preventive maintenance schedule",
                "description": "Set up a recurring maintenance task for a property or unit.",
                "realEndpoint": "POST /api/maintenance-schedules",
            },
        ],
    },
    {
        "category": "Cleaning",
        "forms": [
            {
                "name": "Unit turnover checklist - cleaning",
                "description": "The real cleaning-only view of a unit turnover checklist "
                                "(kitchen, bathroom, carpets, windows, closets) - see a turnover "
                                "inspection with ?role=cleaning.",
                "realEndpoint": "GET /api/inspections/{inspection_id}?role=cleaning",
            },
        ],
    },
    {
        "category": "Inspections",
        "forms": [
            {
                "name": "New inspection",
                "description": "Create a move-in, move-out, or annual unit inspection.",
                "realEndpoint": "POST /api/inspections",
            },
        ],
    },
    {
        "category": "Leasing",
        "forms": [
            {
                "name": "New lease",
                "description": "Create a new lease for a unit.",
                "realEndpoint": "POST /api/leases",
            },
            {
                "name": "Screening request",
                "description": "Start a tenant screening request for an applicant.",
                "realEndpoint": "POST /api/screening",
            },
            {
                "name": "Custom rental application questions",
                "description": "Define or view a property's own rental application questions.",
                "realEndpoint": "GET/POST /api/application-questions",
            },
            {
                "name": "Lease renewal offer",
                "description": "Offer a renewal incentive on an existing lease.",
                "realEndpoint": "POST /api/leases/{lease_id}/renewal-incentive",
            },
            {
                "name": "Write with AI",
                "description": "Draft an email or SMS to a resident, optionally grounded in their real lease.",
                "realEndpoint": "POST /api/write-assist/draft",
            },
        ],
    },
    {
        "category": "Finance",
        "forms": [
            {
                "name": "Record a payment",
                "description": "Manually record a resident payment.",
                "realEndpoint": "POST /api/payments",
            },
            {
                "name": "New bank reconciliation line",
                "description": "Log a real bank statement line for reconciliation.",
                "realEndpoint": "POST /api/reconciliation",
            },
            {
                "name": "RUBS utility bill",
                "description": "Allocate a real utility bill across occupied units.",
                "realEndpoint": "POST /api/rubs/generate",
            },
            {
                "name": "Bill scan",
                "description": "Scan a real bill photo for a draft vendor/amount/date extraction.",
                "realEndpoint": "POST /api/bill-scan/extract",
            },
            {
                "name": "Trust accounting",
                "description": "Real trust-fund balance and commingling check, based on how staff classify bank lines.",
                "realEndpoint": "GET /api/trust-accounting/balance",
            },
            {
                "name": "Fixed asset / capital project",
                "description": "Track a real property asset's expected end-of-life, or plan a larger capital project.",
                "realEndpoint": "POST /api/fixed-assets",
            },
            {
                "name": "Predictive analytics",
                "description": "Real churn-risk scoring and historical vacancy patterns.",
                "realEndpoint": "GET /api/predictive/churn-risk",
            },
        ],
    },
    {
        "category": "Staff & Operations",
        "forms": [
            {
                "name": "New on-call shift",
                "description": "Schedule a staff member's on-call rotation coverage.",
                "realEndpoint": "POST /api/on-call/shifts",
            },
            {
                "name": "Custom roles & permissions",
                "description": "Define named roles and assign them to staff members.",
                "realEndpoint": "GET/POST /api/custom-roles",
            },
            {
                "name": "Custom fields",
                "description": "Define custom fields for units, leases, vendors, or tickets.",
                "realEndpoint": "GET/POST /api/custom-fields/definitions",
            },
            {
                "name": "New vendor",
                "description": "Add a vendor for maintenance/repair work.",
                "realEndpoint": "POST /api/vendors",
            },
            {
                "name": "Package/delivery log",
                "description": "Log a package that's arrived for a resident.",
                "realEndpoint": "POST /api/packages",
            },
        ],
    },
]


@router.get("")
async def list_form_catalog(user: dict = Depends(require_staff)):
    return {"categories": FORM_CATALOG}
