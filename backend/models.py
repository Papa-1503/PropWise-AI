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
    type: Literal["move-in", "move-out", "annual"] = "annual"
    items: list[InspectionItemIn]


class PhotoMark(BaseModel):
    x: float
    y: float


# ---------- Maintenance ----------

class TicketCreate(BaseModel):
    propertyId: str
    unitId: str
    title: str
    priority: Literal["normal", "urgent"] = "normal"
    source: Literal["resident", "inspection", "staff"] = "staff"
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
