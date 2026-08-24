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


# ---------- Properties / Units ----------

class UnitIn(BaseModel):
    unitId: str
    status: Literal["occupied", "vacant", "maintenance_hold"] = "vacant"
    rent: float = Field(ge=0, default=0)
    bedrooms: int = Field(ge=0, default=0)
    bathrooms: float = 0

class UnitIn(BaseModel):
    unitId: str
    status: Literal["occupied", "vacant", "maintenance_hold"] = "vacant"
    rent: float = Field(ge=0, default=0)
    bedrooms: int = Field(ge=0, default=0)
    bathrooms: float = 0
    readyToList: bool = True


class PropertyCreate(BaseModel):
    name: str
    address: str = ""
    units: list[UnitIn] = Field(default_factory=list)
class OwnerAssign(BaseModel):
    ownerId: str

class PropertyUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None


class UnitStatusUpdate(BaseModel):
    status: Literal["occupied", "vacant", "maintenance_hold"]


# ---------- Leases ----------

class LeaseCreate(BaseModel):
    propertyId: str
    unitId: str
    residentName: str
    residentEmail: Optional[str] = None
    startDate: str  # ISO date string, parsed on write
    endDate: str
    rent: float = Field(ge=0, default=0)
    renewalStatus: Literal["not_sent", "sent", "signed"] = "not_sent"


class LeaseUpdate(BaseModel):
    renewalStatus: Optional[Literal["not_sent", "sent", "signed"]] = None
    endDate: Optional[str] = None
    balance: Optional[float] = None


# ---------- Auth ----------

class UserRegister(BaseModel):
    email: str
    password: str
    name: str
    role: Literal["staff", "tenant"] = "tenant"
    # tenant accounts should be scoped to the unit they live in
    propertyId: Optional[str] = None
    unitId: Optional[str] = None


class UserLogin(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    id: str
    email: str
    name: str
    role: Literal["staff", "tenant"]
    propertyId: Optional[str] = None
    unitId: Optional[str] = None
class UserRegister(BaseModel):
    email: str
    password: str
    name: str
    role: Literal["staff", "tenant", "owner"] = "tenant"
    propertyId: Optional[str] = None
    unitId: Optional[str] = None


class UserOut(BaseModel):
    id: str
    email: str
    name: str
    role: Literal["staff", "tenant", "owner"]
    propertyId: Optional[str] = None
    unitId: Optional[str] = None

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
    active: bool = True


class VendorAssign(BaseModel):
    vendorId: str
    estimatedCost: Optional[float] = None
    estimatedArrivalHours: Optional[float] = None
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


# ---------- Payments / Collections ----------
#
# Deliberately minimal — this is a rent-charge/payment ledger, not a real
# payments processor. It tracks what's owed and what's been recorded as
# paid; it doesn't move money. Wire an actual processor (Stripe, etc.)
# behind `PaymentRecord` if you want this to handle real transactions.

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


class DocumentSign(BaseModel):
    signedByName: str
    
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


class BankLineMatch(BaseModel):
    chargeId: str

class ApplicantScoreUpdate(BaseModel):
    creditScore: Optional[int] = None
    incomeToRentRatio: Optional[float] = None
    priorEvictions: Optional[int] = None
    rentalHistoryMonths: Optional[int] = None
    notes: Optional[str] = None

class DashboardPreferencesUpdate(BaseModel):
    visibleWidgets: list[str]
    widgetOrder: list[str]
# ---------- Workflows ----------

class WorkflowAction(BaseModel):
    type: Literal["send_email", "create_task", "create_turnover_checklist", "assign_user", "set_status", "webhook"]
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
