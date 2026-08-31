from typing import Optional, Literal
from pydantic import BaseModel, Field


# ---------- Inspections ----------

class InspectionItemIn(BaseModel):
    id: str
    room: str
    description: str = ""
    status: Literal["pass", "flag", "fail", "pending"] = "pending"


class InspectionCreate(BaseModel):
    propertyId: str
    unitId: str
    inspectorName: str = ""
    type: Literal["move-in", "move-out", "annual", "turnover"] = "annual"
    
    items: list[InspectionItemIn]


class PhotoMark(BaseModel):
    x: float
    y: float
class ItemStatusUpdate(BaseModel):
    status: Literal["pass", "flag", "fail", "pending"]
    description: Optional[str] = None


class RepairItemCreate(BaseModel):
    """P14: a reference catalog entry - one common damage type mapped
    to a plain-language part name, a staff-entered labor-hours
    estimate, and a search query string. Deliberately does NOT store
    a live price or a specific product URL - per the roadmap's own
    revised scope, this constructs a retailer SEARCH link at request
    time (see repair_estimate_service.py), not a scraped/API-fetched
    price or a curated product URL that could go stale. No API keys,
    no partner access, nothing to break if a retailer changes their
    backend - the tradeoff, stated honestly, is the tenant sees a
    search results page rather than one guaranteed price, so the
    estimate's real accuracy still rests on the staff-entered
    labor/part figures here, with the link serving as a transparency
    tool, not the pricing source of truth."""
    damageType: str
    partName: str
    laborHours: float = Field(ge=0)
    searchQuery: str
    category: str  # matches a LaborRateCreate.category for the $/hour lookup
    usefulLifeYears: Optional[float] = Field(default=None, ge=0)
    # ^ P15: HUD life-expectancy depreciation input - how many years
    # this item type is expected to last before normal wear and tear
    # alone would have required replacement anyway. Optional here
    # (not every damage type needs depreciation math - a one-time
    # consumable has none), but required for a real deposit-deduction
    # calculation to run - see deposit_pipeline.py.


class LaborRateCreate(BaseModel):
    category: str
    hourlyRate: float = Field(ge=0)

# ---------- Maintenance ----------

class TicketCreate(BaseModel):
    propertyId: str
    unitId: str
    title: str
    priority: Literal["normal", "urgent"] = "normal"
    source: Literal["resident", "inspection", "staff", "preventive_maintenance"] = "staff"
    sourceInspectionId: Optional[str] = None
    room: Optional[str] = None
    assignee: Optional[str] = None
    category: Literal["plumbing", "electrical", "hvac", "general", "landscaping", "locksmith"] = "general"


class TicketUpdate(BaseModel):
    status: Optional[Literal["open", "in_progress", "done"]] = None
    assignee: Optional[str] = None
    priority: Optional[Literal["normal", "urgent"]] = None


class TicketSatisfactionSubmit(BaseModel):
    """Real resident satisfaction signal on a closed maintenance
    ticket - the genuine input review/reputation-management logic
    needs to actually gate anything on ('flag unhappy ones
    internally', per the original Notion backlog phrasing). Nothing
    in this app tracked resolution satisfaction before this - without
    it, there was no honest signal to build the rest of that feature
    on. Posting an external review (Google/Yelp) is explicitly out of
    scope here - that needs a real external platform API and account
    this app doesn't have; this is the internal-facing half only."""
    rating: int = Field(ge=1, le=5)
    comment: Optional[str] = None


# ---------- AI Copilot ----------

class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class CopilotRequest(BaseModel):
    message: str
    propertyId: Optional[str] = None
    history: list[ChatTurn] = Field(default_factory=list)


class CopilotResponse(BaseModel):
    answer: str
    sources: list[str] = Field(default_factory=list)


class FaqRequest(BaseModel):
    """Tenant-facing auto-responder, deliberately separate from
    CopilotRequest above rather than reusing the staff copilot
    endpoint directly - propertyId/unitId are NOT accepted here at
    all, unlike the staff copilot which takes an explicit propertyId.
    Scope is derived entirely from the authenticated tenant's own user
    record (never trusted from the request body), so there's no way
    for a resident to ask about a different unit's data even by
    passing different values - the same never-trust-client-submitted-
    scope principle already established in auth.py's tenant activation
    flow."""
    message: str
    history: list[ChatTurn] = Field(default_factory=list)


# ---------- Properties / Units ----------

class UnitIn(BaseModel):
    unitId: str
    status: Literal["occupied", "vacant", "maintenance_hold"] = "vacant"
    rent: float = Field(ge=0, default=0)
    bedrooms: int = Field(ge=0, default=0)
    bathrooms: float = 0
    readyToList: bool = True
    squareFootage: Optional[float] = Field(default=None, ge=0)
    # ^ Genuinely missing before RUBS (Ratio Utility Billing System)
    # needed it - square footage is the single most common real RUBS
    # allocation basis, and there was nothing to allocate against
    # without this field. Optional, not required, since it's a real
    # gap in existing unit records this doesn't retroactively force
    # staff to fill in before using the rest of the app.


class PropertyCreate(BaseModel):
    name: str
    address: str = ""
    units: list[UnitIn] = Field(default_factory=list)
class OwnerAssign(BaseModel):
    ownerId: str

class PropertyUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None


class RentRulesUpdate(BaseModel):
    """Field names match exactly what routers/admin.py's run_late_fee_check
    already reads (prop.get("lateFeeGraceDays", ...), prop.get("lateFeeAmount", ...))
    — this endpoint is what was genuinely missing: the automation logic
    already existed and already reads per-property values with sensible
    defaults; there was just no way for staff to ever set them."""
    lateFeeGraceDays: Optional[int] = Field(default=None, ge=0, le=60)
    lateFeeAmount: Optional[float] = Field(default=None, ge=0)
    dueDay: Optional[int] = Field(default=None, ge=1, le=28)
    escalationDays: Optional[int] = Field(default=None, ge=0, le=90)
    # ^ days AFTER a late fee is applied, with the charge still unpaid,
    # before it's automatically escalated — read by run_escalation_check.


class TelephonyConfigUpdate(BaseModel):
    """The Twilio phone number that routes to this property's after-
    hours on-call line. Twilio's Voice webhook (routers/telephony.py)
    looks up the property by matching the incoming call's `To` number
    against this field, so it knows whose on-call rotation to check.
    Each property that wants after-hours routing needs its own real
    Twilio number purchased/configured in the Twilio console first —
    this field just tells RentFlow which number maps to which
    property, it doesn't provision the number itself."""
    twilioNumber: Optional[str] = None
    afterHoursStart: Optional[str] = Field(default=None, description="24h HH:MM, e.g. '18:00'")
    afterHoursEnd: Optional[str] = Field(default=None, description="24h HH:MM, e.g. '08:00'")


class UnitStatusUpdate(BaseModel):
    status: Literal["occupied", "vacant", "maintenance_hold"]


class UnitDetailsUpdate(BaseModel):
    """Editing a unit's actual details (rent, bed/bath) — distinct from
    UnitStatusUpdate above, which only ever covered occupancy status.
    No endpoint existed for this before Priority 48."""
    rent: Optional[float] = None
    bedrooms: Optional[int] = None
    bathrooms: Optional[float] = None
    squareFootage: Optional[float] = None


# ---------- Leases ----------

class LeaseCreate(BaseModel):
    propertyId: str
    unitId: str
    residentName: str
    residentEmail: Optional[str] = None
    residentPhone: Optional[str] = None
    startDate: str  # ISO date string, parsed on write
    endDate: str
    rent: float = Field(ge=0, default=0)
    renewalStatus: Literal["not_sent", "sent", "signed"] = "not_sent"
    insuranceRequired: bool = False
    depositAmount: float = Field(ge=0, default=0)


class LeaseUpdate(BaseModel):
    renewalStatus: Optional[Literal["not_sent", "sent", "signed"]] = None
    endDate: Optional[str] = None
    balance: Optional[float] = None
    insuranceRequired: Optional[bool] = None


class RenewalIncentiveOffer(BaseModel):
    """A real, specific renewal incentive staff can attach to a lease -
    e.g. '$100 off first month', 'no rent increase', 'free parking spot
    for 6 months' - rather than the generic 'contact us about renewal'
    notice run_lease_renewal_check already sends on its own. description
    is free text (staff know their own real incentive programs far
    better than any fixed enum this app could offer); status tracks
    whether the resident has actually responded to it."""
    description: str
    expiresAt: Optional[str] = None  # ISO date string - offer good until this date


class RenewalIncentiveResponse(BaseModel):
    status: Literal["accepted", "declined"]


class InsurancePolicyUpdate(BaseModel):
    """Staff-entered policy details, separate from the actual proof-of-
    insurance document upload (POST /{lease_id}/insurance-proof) - a
    resident might call in their policy number before the certificate
    itself is on file, or vice versa, so these are independent, not
    bundled into one required step."""
    carrier: Optional[str] = None
    policyNumber: Optional[str] = None
    expirationDate: Optional[str] = None  # ISO date string


# ---------- Auth ----------

class UserLogin(BaseModel):
    email: str
    password: str


class TenantActivate(BaseModel):
    """The public resident sign-up flow, replacing raw Property ID/Unit ID
    fields with a single invite code — a real security fix (Priority 34),
    not just a UX rename. The invite code is generated server-side when
    staff create a lease and is the ONLY thing that determines which
    unit an account binds to; no client-submitted propertyId/unitId is
    trusted for this purpose at all."""
    inviteCode: str
    email: str
    password: str
    name: str


class StaffOwnerRegister(BaseModel):
    """The real model for register-staff/register-owner - both
    staff-authenticated-only endpoints, confirmed via a direct grep
    to be their sole real usage. Replaces the old UserRegister, which
    carried role/propertyId/unitId fields that were genuinely dead on
    every real call site: role was always silently overwritten by the
    endpoint's own forced_role regardless of what was submitted (see
    routers/auth.py's _create_staff_or_owner), and propertyId/unitId
    are never read anywhere for staff or owner accounts - confirmed
    directly, since owners are scoped via a real reverse lookup
    (properties_col.ownerId == user id, see routers/owners.py), never
    via a field stored on the user record itself. Not a live security
    bug on its own (both endpoints already require an authenticated
    staff caller), but genuinely confusing API-contract clutter that
    could mislead anyone reviewing the schema without also reading
    the enforcement logic underneath it."""
    email: str
    password: str
    name: str


class UserOut(BaseModel):
    id: str
    email: str
    name: str
    role: Literal["staff", "tenant", "owner"]
    propertyId: Optional[str] = None
    unitId: Optional[str] = None
    autopayEnabled: bool = False


class ProfileUpdate(BaseModel):
    name: str


class PasswordChange(BaseModel):
    currentPassword: str
    newPassword: str


class PushSubscriptionKeys(BaseModel):
    p256dh: str
    auth: str


class PushSubscriptionCreate(BaseModel):
    """Matches exactly what the browser's PushSubscription.toJSON() produces."""
    endpoint: str
    keys: PushSubscriptionKeys

class TokenResponse(BaseModel):
    accessToken: str
    tokenType: str = "bearer"
    user: UserOut


# ---------- AI Actions ----------
#
# IMPORTANT: `confidence` and projected outcome numbers here are Claude's
# reasoned estimate given current portfolio data — not an actuarial model
# trained on historical outcomes. Treat these as "AI's best judgment,"
# shown to staff for a human approve/reject decision, not as guaranteed
# figures. Don't let the UI present them as statistically validated
# without building real historical modeling first.

class ActionCreate(BaseModel):
    """Internal — used by the generation engine, not exposed directly to clients."""
    propertyId: Optional[str] = None
    type: Literal["renewal_campaign", "rent_adjustment", "collections_reminder", "maintenance_followup"]
    title: str
    priority: Literal["high", "medium", "low"]
    rationale: str
    projectedOutcome: str
    estimatedValue: Optional[float] = None  # numeric $ estimate, when applicable, for aggregation
    affectedUnitIds: list[str] = Field(default_factory=list)
    confidence: int  # 0-100, AI-estimated — see note above
    riskLevel: Literal["low", "medium", "high"] = "low"
    plannedSteps: list[str] = Field(default_factory=list)


class ActionDecision(BaseModel):
    decision: Literal["approve", "reject", "edit"]
    editedTitle: Optional[str] = None
    note: Optional[str] = None


# ---------- Vendors ----------
#
# NOTE: `distanceMiles` and `avgArrivalHours` are manually maintained
# fields on the vendor record, not a live calculation — we don't
# geocode vendor or property addresses. If you want real distance/ETA,
# that needs a geocoding + routing integration (e.g. Google Maps
# Distance Matrix) layered on top of this.

class VendorCreate(BaseModel):
    name: str
    category: Literal["plumbing", "electrical", "hvac", "general", "landscaping", "locksmith"]
    rating: float = Field(ge=0, le=5, default=4.5)
    distanceMiles: Optional[float] = None
    avgArrivalHours: Optional[float] = None
    baseCost: Optional[float] = Field(ge=0, default=None)
    phone: Optional[str] = None
    email: Optional[str] = None
    active: bool = True


class VendorAssign(BaseModel):
    vendorId: str
    estimatedCost: Optional[float] = None
    estimatedArrivalHours: Optional[float] = None
    note: Optional[str] = None


class SupplyCreate(BaseModel):
    """P17 Phase 1: manual entry + vendor-linked low-stock alerts, per
    the reconciled roadmap's own scoping. vendorId is optional at
    creation - a supply can exist before staff have decided who to
    order it from, but reorderThreshold is what actually drives the
    low-stock check below, so it's required, not optional with a
    silent default that could mean "never alert" without anyone
    intending that."""
    propertyId: str
    name: str
    category: str
    quantity: int = Field(ge=0, default=0)
    reorderThreshold: int = Field(ge=0)
    vendorId: Optional[str] = None
    vendorSku: Optional[str] = None
    unitCost: Optional[float] = Field(ge=0, default=None)


class SupplyUpdate(BaseModel):
    quantity: Optional[int] = Field(default=None, ge=0)
    reorderThreshold: Optional[int] = Field(default=None, ge=0)
    vendorId: Optional[str] = None
    vendorSku: Optional[str] = None
    unitCost: Optional[float] = Field(default=None, ge=0)


class SupplyQuantityAdjust(BaseModel):
    """The real, actual-usage entry point - staff log a quantity
    CHANGE (e.g. -3 after using 3 units, +50 after a delivery
    arrives), not a full quantity overwrite. Overwriting the absolute
    number is easy to get wrong (a staff member typing what they
    think the new total is, rather than what actually changed) in a
    way a signed delta isn't."""
    delta: int
    note: Optional[str] = None


# ---------- AI Photo Recognition ----------

class DetectedIssue(BaseModel):
    label: str
    severity: Literal["low", "medium", "high"]
    description: str


class PhotoAnalysisResult(BaseModel):
    summary: str
    issues: list[DetectedIssue] = Field(default_factory=list)


# ---------- Notifications ----------
#
# Notifications are created internally (by other routers, via
# notifications_service.py) in response to real events — never directly
# by a client. There is no public "create notification" endpoint.

class NotificationOut(BaseModel):
    id: str
    type: Literal["urgent_ticket", "vendor_assigned", "payment_received", "ai_action_suggested", "lease_expiring", "general"]
    title: str
    body: str
    link: Optional[str] = None
    read: bool = False
    createdAt: str


# ---------- Social feed (internal staff comms) ----------

class PostCreate(BaseModel):
    content: str = Field(min_length=1, max_length=2000)
    category: Literal["general", "announcement", "shoutout"] = "general"
    taggedUserId: Optional[str] = None  # for "shoutout" recognition posts


class CommentCreate(BaseModel):
    content: str = Field(min_length=1, max_length=1000)


class PostOut(BaseModel):
    id: str
    authorId: str
    authorName: str
    content: str
    category: Literal["general", "announcement", "shoutout"]
    taggedUserId: Optional[str] = None
    taggedUserName: Optional[str] = None
    reactionCount: int = 0
    reactedByMe: bool = False
    commentCount: int = 0
    createdAt: str


class CommunityPostCreate(BaseModel):
    """Real resident community board, genuinely separate from
    social.py's staff feed above - that feed is explicitly internal-
    only per its own module docstring, so this is a distinct
    collection and router, not the same feed reopened to tenants.
    Scoped per-property (a resident should never see a different
    building's board) with the propertyId taken from the
    authenticated user's own record, same never-trust-client-
    submitted-scope pattern used elsewhere - never from this payload.
    No shoutout/tagging concept here - that's a staff-internal
    recognition idea, not something resident-appropriate."""
    content: str = Field(min_length=1, max_length=2000)
    category: Literal["general", "announcement"] = "general"


class CommunityCommentCreate(BaseModel):
    content: str = Field(min_length=1, max_length=1000)


# ---------- Payments / Collections ----------
#
# Deliberately minimal — this is a rent-charge/payment ledger, not a real
# payments processor. It tracks what's owed and what's been recorded as
# paid; it doesn't move money. Wire an actual processor (Stripe, etc.)
# behind `PaymentRecord` if you want this to handle real transactions.

class RubsBillCreate(BaseModel):
    """RUBS - Ratio Utility Billing System. One real utility bill (water,
    sewer, trash, etc.) for a whole property, allocated across its
    occupied units by a real, staff-chosen method rather than split
    equally by default, since equal split is rarely what a real
    property actually wants. squareFootage-based allocation depends on
    UnitIn.squareFootage actually being set - genuinely missing from
    the unit model before this feature, added alongside it since RUBS
    is the reason it's needed. bedroomCount allocates by each unit's
    real bedrooms field (already existed); equalSplit divides evenly
    across occupied units - the one method that needs no real per-unit
    data at all, useful for properties that haven't recorded square
    footage yet."""
    propertyId: str
    utilityType: str  # e.g. "water", "sewer", "trash"
    totalAmount: float = Field(gt=0)
    billingPeriod: str  # 'YYYY-MM'
    allocationMethod: Literal["squareFootage", "bedroomCount", "equalSplit"] = "equalSplit"
    dueDate: str  # ISO date string


class ChargeCreate(BaseModel):
    propertyId: str
    unitId: str
    leaseId: Optional[str] = None
    amountDue: float = Field(gt=0)
    dueDate: str  # ISO date string
    description: str = "Monthly rent"


class PaymentRecord(BaseModel):
    amountPaid: float = Field(gt=0)
    paidDate: Optional[str] = None  # defaults to now if omitted
    method: Optional[Literal["ach", "card", "check", "cash", "other"]] = None
    note: Optional[str] = None

class PaymentReturn(BaseModel):
    amount: float = Field(gt=0)
    reason: Optional[str] = None
    
class CheckoutSessionCreate(BaseModel):
    successUrl: Optional[str] = None
    cancelUrl: Optional[str] = None


class AutopayEnroll(BaseModel):
    """Enrolls a tenant in recurring ACH autopay. Doesn't take a bank
    account directly — that would mean this app's own backend handling
    raw account/routing numbers, which is both a real security
    liability and outside NACHA/Stripe's intended integration pattern.
    Instead, the tenant links their bank account through Stripe's own
    hosted flow (a SetupIntent, confirmed client-side with Stripe.js —
    see POST /setup-intent below), and only the resulting Stripe
    paymentMethodId - a reference token, never the real account
    details - ever reaches this backend."""
    paymentMethodId: str


class LeadCreate(BaseModel):
    name: str
    email: str
    phone: Optional[str] = None
    propertyId: Optional[str] = None
    unitId: Optional[str] = None
    message: Optional[str] = None


class LeadStatusUpdate(BaseModel):
    status: Literal["new", "toured", "applied", "signed", "declined"]
    
class DocumentCreate(BaseModel):
    tenantEmail: str
    leaseId: Optional[str] = None
    title: str
    content: str
    documentType: Literal["lease", "renewal", "deposit_statement"] = "lease"


class DocumentSign(BaseModel):
    signedByName: str


class KbArticleCreate(BaseModel):
    """Internal staff-only content - SOPs, past issue resolutions,
    vendor contacts, troubleshooting guides. Deliberately separate
    from DocumentCreate above (tenant lease documents, e-signature
    flow) and from the tenant-facing FAQ (ai_copilot.py's /faq, which
    answers from a resident's own real lease/ticket data, not from
    static articles) - three genuinely different content types that
    happen to superficially resemble each other."""
    title: str
    category: str
    content: str


class KbArticleUpdate(BaseModel):
    title: Optional[str] = None
    category: Optional[str] = None
    content: Optional[str] = None


class CustomFieldDefinitionCreate(BaseModel):
    """P18: arbitrary staff-defined fields on real entities (units,
    leases, vendors, tickets) - genuinely absent before this, confirmed
    by a direct search. Deliberately a real, validated definitions
    registry rather than letting staff write arbitrary keys directly
    onto a record: a defined field has a real type staff chose (text,
    number, boolean, date), so a value set later can actually be
    validated against it instead of silently accepting anything.
    entityType controls which real collection this field applies to -
    checked directly against a real, closed list of this app's actual
    entity types, not an arbitrary string that could reference
    something that doesn't exist."""
    entityType: Literal["unit", "lease", "vendor", "ticket"]
    fieldName: str
    fieldType: Literal["text", "number", "boolean", "date"]
    required: bool = False


class CustomFieldValueSet(BaseModel):
    fieldName: str
    value: str | float | bool | None = None


class CommunicationTemplateCreate(BaseModel):
    """P18: reusable email/SMS templates with real variable
    substitution, rather than staff retyping (or copy-pasting and
    editing) the same message every time. Placeholders use
    {{fieldName}} syntax, substituted against a real lease's actual
    fields at render time (see communication_templates.py) - never a
    separate, hand-maintained set of merge fields that could drift
    from what a lease record actually contains."""
    name: str
    channel: Literal["email", "sms"]
    subject: Optional[str] = None  # ignored for sms
    body: str


class CommunicationTemplateUpdate(BaseModel):
    name: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None


# P18: real custom roles & permissions - a genuine, closed set of
# permission strings mapping to actual real operational boundaries a
# property management team would want to separate, not an open-ended
# arbitrary string a role definition could set to anything. Chosen to
# reflect real, meaningful groupings already visible in this app's own
# router structure (leasing vs. maintenance vs. finance vs. staff
# management), not an exhaustive per-endpoint permission list, which
# would be far too granular to actually configure in practice.
PERMISSION_CHOICES = (
    "leasing",       # leases, screening, leads
    "maintenance",   # tickets, inspections, vendors, supplies
    "finance",       # payments, budgets, reconciliation, RUBS
    "communications",  # communications, community board, templates
    "staff_management",  # staff assignments, on-call rotation
    "reports",       # dashboard, audit log, capital planning
)


class CustomRoleCreate(BaseModel):
    """A real, named role a staff member can be assigned, scoping their
    access to a real subset of PERMISSION_CHOICES rather than the
    default blanket staff access every account has today. Deliberately
    additive to the existing role system, not a replacement -
    role='staff' on the user record is completely unchanged; this is a
    separate, optional overlay (see StaffCustomRoleAssign below) that
    a NEW dependency (require_permission, auth.py) can check, while
    every existing require_staff-protected endpoint (177 of them,
    confirmed via a direct count before scoping this) keeps working
    completely unchanged, with no migration risk to any of them."""
    name: str
    permissions: list[Literal["leasing", "maintenance", "finance", "communications", "staff_management", "reports"]]


class CustomRoleUpdate(BaseModel):
    name: Optional[str] = None
    permissions: Optional[list[Literal["leasing", "maintenance", "finance", "communications", "staff_management", "reports"]]] = None


class StaffCustomRoleAssign(BaseModel):
    customRoleId: Optional[str] = None
    # ^ None explicitly means "remove the custom role, fall back to
    # full staff access" - a real, deliberate way to unset it, not
    # just omitting the field (which PATCH-style endpoints elsewhere in
    # this app already treat as "leave unchanged", so an explicit
    # null here needs its own real handling, done in the endpoint).

class ScreeningRequestCreate(BaseModel):
    leadId: Optional[str] = None
    applicantName: str
    applicantEmail: str
    propertyId: Optional[str] = None
    unitId: Optional[str] = None


class ScreeningStatusUpdate(BaseModel):
    status: Literal["pending", "in_progress", "passed", "failed", "manual_review"]
    notes: Optional[str] = None

class BankLineCreate(BaseModel):
    propertyId: str
    date: str
    description: str
    amount: float
    matchedChargeId: Optional[str] = None
    category: Optional[str] = None


class BankLineMatch(BaseModel):
    chargeId: str


class BudgetCreate(BaseModel):
    """One budget line: what a property expects to spend on one
    category in one calendar month. period is 'YYYY-MM' rather than a
    real date range - simpler, sortable as a plain string, and avoids
    timezone ambiguity around month boundaries that a stored datetime
    range would introduce for something that's fundamentally a
    calendar-month concept, not a precise instant."""
    propertyId: str
    category: str
    period: str  # 'YYYY-MM', e.g. '2026-09'
    budgetedAmount: float = Field(ge=0)


class FixedAssetCreate(BaseModel):
    """P27: a real major property asset - roof, HVAC system, water
    heater, etc. - tracked with install date and expected lifespan so
    end-of-life can be proactively flagged, distinct from the reactive
    maintenance-ticket system already in this app. Reuses the same
    real straight-line-lifespan concept as P14/P15's repair-item
    usefulLifeYears, applied here at the whole-asset level rather than
    a per-damage-instance level."""
    propertyId: str
    unitId: Optional[str] = None  # None for a property-wide asset (e.g. a shared roof)
    name: str
    category: str
    installDate: str  # ISO date string
    expectedLifespanYears: float = Field(gt=0)
    replacementCost: Optional[float] = Field(default=None, ge=0)


class FixedAssetUpdate(BaseModel):
    name: Optional[str] = None
    replacementCost: Optional[float] = Field(default=None, ge=0)


class CapitalProjectCreate(BaseModel):
    propertyId: str
    title: str
    projectedCost: float = Field(ge=0)
    targetDate: str  # ISO date string
    status: Literal["planned", "in_progress", "complete"] = "planned"
    relatedAssetId: Optional[str] = None
    budgetPeriod: Optional[str] = None
    # ^ P27's own stated connection to the Budgeting module (P21,
    # already built this session): a planned capital project can name
    # which budget period ('YYYY-MM') it's meant to show up under, so
    # staff can cross-reference the two rather than tracking them in
    # two disconnected places.


class CapitalProjectUpdate(BaseModel):
    projectedCost: Optional[float] = Field(default=None, ge=0)
    targetDate: Optional[str] = None
    status: Optional[Literal["planned", "in_progress", "complete"]] = None


class BudgetUpdate(BaseModel):
    budgetedAmount: Optional[float] = Field(default=None, ge=0)


class ApplicantScoreUpdate(BaseModel):
    creditScore: Optional[int] = None
    incomeToRentRatio: Optional[float] = None
    priorEvictions: Optional[int] = None
    rentalHistoryMonths: Optional[int] = None
    notes: Optional[str] = None

class DashboardPreferencesUpdate(BaseModel):
    visibleWidgets: list[str]
    widgetOrder: list[str]


class CustomViewCreate(BaseModel):
    """P18: a real, staff-saved filter/sort/column configuration for a
    real list page (leases, tickets, leads, vendors) - so a leasing
    agent can save 'expiring in 60 days, sorted by rent' as a genuine,
    reusable view instead of re-entering the same filter every time.
    Owned per-staff-member (see the router - always scoped to the
    creating user's own ID, never shared globally by default), since a
    saved view is a personal workflow shortcut, not a shared team
    configuration - real shared views would be a separate, later
    feature with its own real design questions about who can edit a
    shared one."""
    entityType: Literal["lease", "ticket", "lead", "vendor"]
    name: str
    filters: dict = Field(default_factory=dict)
    sortField: Optional[str] = None
    sortDirection: Literal["asc", "desc"] = "asc"
    visibleColumns: list[str] = Field(default_factory=list)


class CustomViewUpdate(BaseModel):
    name: Optional[str] = None
    filters: Optional[dict] = None
    sortField: Optional[str] = None
    sortDirection: Optional[Literal["asc", "desc"]] = None
    visibleColumns: Optional[list[str]] = None


class CustomReportCreate(BaseModel):
    """P18: a real, saved report definition - deliberately a closed set
    of real report TYPES (reportType below), each with its own real,
    safe, hand-written aggregation (see custom_reports.py), not an
    open-ended query builder accepting arbitrary filter/aggregation
    input. An arbitrary user-constructed MongoDB pipeline would be a
    genuine injection and performance risk (an unbounded $lookup or a
    pipeline scanning every document in a large collection with no
    real limit); a closed set of vetted report types with real,
    bounded parameters is the safe version of the same idea."""
    name: str
    reportType: Literal["revenue_by_property", "maintenance_by_category", "occupancy_trend"]
    propertyId: Optional[str] = None
    startDate: Optional[str] = None
    endDate: Optional[str] = None


class ApplicationQuestionCreate(BaseModel):
    """P18: custom rental application questions, per property - reuses
    the exact same real, closed field-type set already proven for
    custom fields (CustomFieldDefinitionCreate) rather than inventing a
    second, parallel type system. A property can define its own real
    application questions (e.g. 'Do you have pets?', 'Move-in date
    preference') beyond the fixed applicantName/applicantEmail every
    screening request already has."""
    propertyId: str
    questionText: str
    fieldType: Literal["text", "number", "boolean", "date"]
    required: bool = False
    order: int = 0


class ApplicationAnswerSubmit(BaseModel):
    answers: dict[str, str | float | bool | None]
    # ^ keyed by the real question's ID (string), validated against
    # its defined fieldType at submission time - see
    # custom_rental_applications.py

# ---------- Workflows ----------

class WorkflowAction(BaseModel):
    type: Literal["send_email", "create_task", "create_turnover_checklist", "assign_user", "route_to_team", "set_status", "webhook"]
    config: dict = Field(default_factory=dict)
    order: int


class WorkflowTrigger(BaseModel):
    event: Literal[
        "lease_created",
        "tenant_moved_out",
        "unit_created",
        "payment_received",
        "payment_returned",
        "work_order_closed",
    ]
    conditions: Optional[dict] = None


class WorkflowCreate(BaseModel):
    name: str
    trigger: WorkflowTrigger
    actions: list[WorkflowAction] = Field(default_factory=list)


class WorkflowUpdate(BaseModel):
    name: Optional[str] = None
    trigger: Optional[WorkflowTrigger] = None
    actions: Optional[list[WorkflowAction]] = None
    status: Optional[Literal["draft", "published", "paused"]] = None


class Workflow(BaseModel):
    id: str
    org_id: str
    name: str
    trigger: WorkflowTrigger
    actions: list[WorkflowAction] = Field(default_factory=list)
    status: Literal["draft", "published", "paused"] = "draft"
    created_at: str = ""
    updated_at: str = ""

# ---------- Staff / Maintenance Tech Assignment ----------

class StaffPropertyAssignment(BaseModel):
    assignedProperties: list[str] = Field(default_factory=list)


class StaffPhoneUpdate(BaseModel):
    """Staff phone number, needed for on-call rotation contact and any
    future after-hours call routing. Kept as its own small model rather
    than folded into StaffPropertyAssignment since it's set by a
    different actor at a different time (a tech setting their own
    contact info, vs. a manager assigning properties)."""
    phone: str


class OnCallShiftCreate(BaseModel):
    """A single on-call shift: one staff member covering one or more
    properties for a time window. Recurring rotations are modeled as
    multiple shifts (e.g. one created per week), not as a separate
    recurrence-rule concept — simpler to reason about, and manual
    swaps/overrides are then just deleting or editing one shift rather
    than needing special-case override logic layered on top of a
    recurrence engine."""
    userId: str
    propertyIds: list[str] = Field(default_factory=list)
    startTime: str  # ISO datetime string, parsed on write
    endTime: str
    note: Optional[str] = None


class OnCallShiftUpdate(BaseModel):
    userId: Optional[str] = None
    propertyIds: Optional[list[str]] = None
    startTime: Optional[str] = None
    endTime: Optional[str] = None
    note: Optional[str] = None


class TimeEntryCreate(BaseModel):
    hours: float = Field(gt=0)
    note: Optional[str] = None
# ---------- Preventive Maintenance Schedules ----------

class MaintenanceScheduleCreate(BaseModel):
    propertyId: str
    unitId: Optional[str] = None  # omit for property-wide items (e.g. shared HVAC, common areas)
    title: str
    category: Literal["plumbing", "electrical", "hvac", "general", "landscaping", "locksmith"] = "general"
    intervalDays: int = Field(gt=0)
    nextDueDate: str  # ISO date string


class MaintenanceScheduleUpdate(BaseModel):
    title: Optional[str] = None
    intervalDays: Optional[int] = None
    nextDueDate: Optional[str] = None
    active: Optional[bool] = None


# ---------- Unified Communication Hub ----------
#
# Step 1 of the communication hub: data model + manual logging only.
# Real SMS/email sending (Twilio, SendGrid) comes in later steps — for
# now this just gives staff one merged timeline per unit/tenant, and a
# way to log a communication that happened outside the app (a phone
# call, an in-person conversation) alongside ones sent through it later.

class CommunicationCreate(BaseModel):
    propertyId: str
    unitId: str
    channel: Literal["email", "sms", "call"]
    direction: Literal["outbound", "inbound"] = "outbound"
    subject: Optional[str] = None
    body: str


class SendEmailCommunication(BaseModel):
    propertyId: str
    unitId: str
    to: str
    subject: str
    body: str


class SendSmsCommunication(BaseModel):
    propertyId: str
    unitId: str
    to: str  # E.164 format, e.g. +15551234567
    body: str


class GroupMessageSend(BaseModel):
    """Real dynamic message grouping, scoped honestly to what the data
    actually supports. propertyId (a real building/property) and
    occupancyStatus/renewalStatus (real, already-stored lease fields)
    are genuine group targets. Floor is deliberately NOT one of them -
    no floor field exists anywhere on the unit model, and this app's
    real unit IDs (confirmed from actual test data: "251", "19-212",
    "500") don't follow any single, safely-inferrable numbering
    convention that floor could be derived from without risking a
    wrong guess. Rather than fake a floor grouping from an assumption
    that might not hold, this ships the group targets that are
    actually real and correct."""
    propertyId: str
    channel: Literal["email", "sms"]
    subject: Optional[str] = None  # required for email, ignored for sms
    body: str
    occupancyStatus: Optional[Literal["occupied", "vacant", "maintenance_hold"]] = None
    renewalStatus: Optional[Literal["not_sent", "sent", "signed"]] = None


# ---------- Admin ----------

class AdminKeyPayload(BaseModel):
    """Shared secret for admin trigger endpoints, sent in the request body
    rather than a URL query parameter — query params can leak via browser
    history, server access logs, and proxy/CDN caching."""
    key: str
