# RentFlow AI — Consolidated Roadmap (reconciled Aug 30, 2026)

## What this file is

Two separate tracking efforts existed for this same repo, neither
aware of the other: a detailed, priority-numbered log
("RentFlow-AI-Roadmap.pdf," last updated Aug 19, 2026) and this
session's own `ROADMAP.md` (rebuilt from scratch today by reading the
Notion backlog and actual code, with no knowledge the PDF existed).

The PDF was initially treated with real skepticism — it referenced
specific database record counts, a 13-property/~1,846-unit scale test,
and files that seemed absent from this sandbox's view of the repo.
That skepticism was **wrong**, confirmed by direct spot-checks against
real git history and live code: the exact broken-title bug it
describes fixing shows up verbatim in this repo's commit log
(`e84ab1e` → `550d457`), the malformed-icon fix, the shortened
ticket-ID fix, `seed_scale_test.py`, `telephony.py`, `oncall.py`,
`budgets.py`, ticket severity scoring, vendor recommendation scoring,
and the tenant reliability score are all genuinely present exactly as
described. This is real, accurate history for this repo — the
skepticism itself is worth recording so a future read of this file
doesn't repeat the same false start.

**Below: every PDF priority, its real status as of today, and what
this session either confirmed, added, or found still genuinely open.**
Items already fully covered in `ROADMAP.md` (the Notion-backlog-phase
tracking) aren't repeated in full here — see that file for the
detailed writeups on those.

---

## Confirmed done (PDF-tracked, spot-checked accurate)

P1 Mobile-friendly app · P2 Workflow automation triggers · P3 MongoDB
Atlas MCP · P4 Auto-assign maintenance to tech · P5 Preventive
maintenance reminders · P6 Unit turnover checklist · P7 Proactive
tenant/payment reminders · P8 Push notifications · P9 Workflow builder
UI · P10 Scale test (13 properties, ~1,846 units) · P11 Building
selector · P28 Owner Portal frontend · P29 Leases management UI · P30
Screening UI · P31 Resident/Unit 360 (Resident 360 done; Unit 360
frontend was deferred — **built this session**, see below) · P32
Mobile rendering fixes · P33 Real routing (React Router) · P34 Account
activation / invite codes · P35 Admin endpoints GET→POST · P36
Accessibility fixes · P37 PWA install setup (icons, theme-color) · P39
Sidebar navigation, dark mode, Ctrl+K search, onboarding tour, toast
system (the "PropWise-inspired" catalog, cross-confirmed against this
session's own independent verification) · P40 Centralized API client
/ localStorage token audit / bulk actions / Kanban board · P43 Leads
pipeline UI · P45 Staff/tech property assignment UI · P46 Preventive
maintenance schedules UI · P47 Bank reconciliation UI · P48 Property
creation/editing UI.

Also confirmed real from the PDF's later additions: ticket
grouping/duplicate detection, vendor assignment scoring, ticket
severity scoring, tenant reliability score, tenant welcome
experience/onboarding email.

## Genuinely completed by THIS session (new since the PDF, or picking
up an explicitly-deferred piece)

- **Unit 360 frontend** — the PDF explicitly deferred this
  ("backend ready, frontend still open"). Built this session as
  `UnitHistoryModal.jsx`, reusing the Resident 360 modal's row
  components, wired into both Leases and the Owner Portal.
- **On-call rotation + after-hours Twilio Voice routing** (PDP's
  "Sub-feature" under P12, explicitly deferred pending a rotation
  scheduler) — real shift CRUD, real signature-verified Voice webhook,
  caller-ID-to-tenant matching, after-hours window logic. A past
  session's attempt at this exact feature never made it into git on
  any branch; this is a genuine rebuild, not a resume.
- **ACH autopay** (listed under P12's "Related Phase 1 items," never
  scoped) — real Stripe ACH Direct Debit, correctly asynchronous,
  never handles raw bank credentials, real webhook settlement
  handling, real recurring trigger.
- **Owner statements/P&L** — the PDF's P13 turned out to already be
  built as part of P28; this session's ROADMAP.md independently
  confirmed the same.
- **Budgeting & Forecasting** (P21) — real per-property/category/month
  budgets with a genuine actual-vs-budgeted report built on real bank
  reconciliation data.
- **Audit trail / activity log** — not explicitly in the PDF; added
  this session, wired into 8 real high-value mutations.
- **Renters insurance tracking**, **dynamic message grouping**,
  **renewal incentive tracking**, **staff knowledge base**, **resident
  community board**, **tenant FAQ auto-responder**, **self-service
  lease renewal portal** (P39/P24 territory), and the **internal half
  of review/reputation management** plus **automated late notices**
  (honest partial credit — see `ROADMAP.md` for the legal-scope
  caveats on both) — none of these were in the PDF at all; all
  independently identified from the Notion backlog and built this
  session.

## Genuinely still open — confirmed absent from the real repo today

Spot-checked directly, not assumed from the PDF's own status marks:

- **P14 Upfront damage cost estimates** (parts+labor, retailer
  search links) — not built.
- **P15 Move-out → deposit-return pipeline** — not built.
- **P16 Vacancy listing syndication** (Zillow/Apartments.com/
  Facebook Marketplace) — not built; still genuinely
  partner/API-gated per the PDF's own research flag. (`ROADMAP.md`'s
  public-listings-feed entry is a real, related, but smaller piece —
  a feed URL, not actual syndication integration.)
- **P17 Supplies/inventory ordering** — not built.
- **P18 Remaining competitive gaps**: AI bill scan, write-with-AI
  assistant, named AI agent personas (P22 scoped this further, still
  not built), AI summaries, custom fields, custom report builder,
  custom roles & permissions, custom rental applications, custom
  views, customized communication templates — all confirmed absent.
- **P19 Deferred**: IoT scaffolding, live bank feed, CRP generation —
  still deferred, nothing changed.
- **P20 AI-guided DIY troubleshooting** on ticket submission — not
  built.
- **P23 Digital lease e-signatures via a real external provider**
  (DocuSign) — not built; genuinely needs a real external account,
  same as the PDF flagged. (Note: this session's self-service renewal
  and the existing lease e-signature flow are RentFlow's own in-house
  signing system, not a DocuSign integration — a different, smaller
  thing than what P23 describes.)
- **P24 Virtual tour integration** (Matterport or similar) — not
  built; needs a real external account.
- **P25 AI fraud detection in screening** (document upload +
  tampering analysis) — not built.
- **P26 Cross-portfolio make-ready board** — not built.
- **P27 Capital projects & fixed-asset planning** — not built.
- **P41 Session security hardening** (HttpOnly cookies instead of
  localStorage, CSP/frame/referrer/permissions headers, public
  Swagger docs decision, explicit per-role authorization test suite)
  — not built; a real, worthwhile security backlog item.
- **P42 Public-vs-internal-beta decision, marketing site, broader
  confirmation/audit-trail/idempotency coverage beyond what's already
  covered, AI Actions reasoning/confidence UI** — not built.
- **P44 Split the public registration schema** to remove the
  unused/misleading `role` field — small, still open.
- **P49 Full user manual** — explicitly gated on everything else
  being done first; still not started, correctly.

## Also still open, cross-referencing `ROADMAP.md`'s own list (not
duplicated from the PDF, since the PDF never covered these)

Call recording + transcription · Package/delivery tracking with OCR ·
Trust accounting · QuickBooks/Xero sync · Predictive analytics (churn,
seasonal vacancy) · RUBS · Smart lock integration · Full tenant-facing
chatbot (Phase 6 scope, beyond the lightweight FAQ responder already
built).
