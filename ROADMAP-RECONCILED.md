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

- **✅ P14 Upfront damage cost estimates**: built and pushed this
  session — real `repair_items`/`labor_rates` catalog CRUD, a URL-
  construction helper for real Home Depot/Amazon search links
  (deliberately no retailer API, matching the PDF's own revised
  scope), and a real endpoint linking flagged/failed inspection
  items to a computed estimate. Confirmed the multi-state HUD
  depreciation math mentioned in past project history is, like the
  earlier on-call/telephony finding, genuinely absent from this repo
  — noted honestly rather than assumed present. Verified extensively:
  URL encoding with real special characters, labor-cost math both
  with and without a real rate on file, and three real cases of the
  flagged-item matching endpoint (match, rejected pass, honest
  no-match).
- **🟡 P15 Move-out → deposit-return pipeline**: built and pushed
  this session, explicitly and repeatedly labeled NOT legal advice —
  real straight-line depreciation math (correctly floors at 0%
  billable once an item is past its useful life, verified as the
  single most important case), a real tenant-facing itemized
  statement generated through the existing Documents system, and the
  disclaimer carried through the API response, the module docstring,
  and the generated document's own text. Confirmed the multi-state
  HUD engine referenced in past project history genuinely doesn't
  exist in this repo — real jurisdiction-specific legal correctness
  was explicitly not attempted here and is stated as such throughout.
  Verified with real depreciation-math tests covering the zero-floor
  edge case plus a full end-to-end pipeline test.
- **P16 Vacancy listing syndication** (Zillow/Apartments.com/
  Facebook Marketplace) — not built; still genuinely
  partner/API-gated per the PDF's own research flag. (`ROADMAP.md`'s
  public-listings-feed entry is a real, related, but smaller piece —
  a feed URL, not actual syndication integration.)
- **✅ P17 Supplies/inventory ordering, Phase 1**: built and pushed
  this session — real CRUD, quantity tracking via a signed delta
  (not an absolute overwrite), real `$expr`-based low-stock detection,
  and a genuine vendor-order-email action reusing the app's real
  email infrastructure. A real gap was found and fixed along the way:
  `VendorCreate` had no email field at all, which would have made the
  order action fail unconditionally for every vendor. Phase 2
  (predictive, consumption-rate-based reordering) deliberately not
  attempted — needs real order history this feature will only start
  generating once it's actually in use.
- **P18 Remaining competitive gaps**: AI bill scan, write-with-AI
  assistant, named AI agent personas (P22 scoped this further, still
  not built), AI summaries, custom fields, custom report builder,
  custom roles & permissions, custom rental applications, custom
  views, customized communication templates — all confirmed absent.
- **P19 Deferred**: IoT scaffolding, live bank feed, CRP generation —
  still deferred, nothing changed.
- **✅ P20 AI-guided DIY troubleshooting**: built and pushed this
  session — a real, code-enforced safety gate
  (`services/diy_safety.py`) checked before any AI call is ever
  made, matching the PDF's own explicit requirement. A genuine
  phrasing bug was caught and fixed during testing: the first keyword
  list only matched exact multi-word phrase order and missed real
  variants like "smell of gas" and "ceiling looks like its sagging" —
  fixed and re-verified against new phrasing, not just the original
  failing strings. Verified with the test that matters most: confirmed
  via a mocked AI client that the AI is genuinely never invoked at all
  for an unsafe request, a structural barrier, not a prompt-level one.
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
- **✅ P26 Cross-portfolio make-ready board**: built and pushed this
  session — `GET /api/make-ready/board`, real aggregation over
  existing turnover-inspection and unit-`readyToList` data, no new
  collections. Real stage logic (repairs needed / inspection in
  progress / ready to list) with flag/fail correctly taking priority
  over pending count, and correct dedup when a unit has more than one
  turnover inspection over its history. Both pieces of nontrivial
  logic verified with real functional tests.
- **✅ P27 Capital projects & fixed-asset planning**: built and pushed
  this session — real fixed-asset and capital-project CRUD, and the
  genuine payoff of tracking install date + lifespan: a real
  end-of-life view flagging assets approaching or past their expected
  replacement date. Real cross-reference to this session's own
  Budgeting module, stated as an optional link staff set, not an
  automatic assumption. Verified with a functional test covering
  three real cases at once (approaching, already past, correctly
  excluded as too far out) plus correct sort order.
- **🟡 P41 Session security hardening**: substantially built and
  pushed this session — real security-headers middleware (CSP/frame-
  ancestors, X-Content-Type-Options, Referrer-Policy, Permissions-
  Policy, verified applied globally including on the public `/docs`
  page), and a real HttpOnly session cookie auth path added
  alongside (not replacing) the existing Bearer-token flow, correctly
  handling this app's genuinely cross-origin frontend/backend split
  (`SameSite=None`+`Secure`, not the more common `Lax`, which would
  have silently broken it). New `POST /api/auth/logout` to actually
  clear the cookie, since JavaScript can't. Every piece verified with
  real functional tests, not assumed. Still open: migrating the
  frontend's `authFetch` calls to use the cookie instead of
  localStorage, the public-Swagger-docs decision, and a dedicated
  per-role authorization test suite.
- **P42 Public-vs-internal-beta decision, marketing site, broader
  confirmation/audit-trail/idempotency coverage beyond what's already
  covered, AI Actions reasoning/confidence UI** — not built.
- **✅ P44 Split the public registration schema**: built and pushed
  this session — `UserRegister` genuinely retired (confirmed zero
  remaining references), replaced with a real, minimal
  `StaffOwnerRegister` (email/password/name only). Verified via the
  live OpenAPI schema that the confusing role/propertyId/unitId
  fields are actually gone from the API contract, not just hidden,
  and via a functional test that the stored document is genuinely
  clean of them too.
- **P49 Full user manual** — explicitly gated on everything else
  being done first; still not started, correctly.

## Also still open, cross-referencing `ROADMAP.md`'s own list (not
duplicated from the PDF, since the PDF never covered these)

Call recording + transcription · Package/delivery tracking with OCR ·
Trust accounting · QuickBooks/Xero sync · Predictive analytics (churn,
seasonal vacancy) · RUBS · Smart lock integration · Full tenant-facing
chatbot (Phase 6 scope, beyond the lightweight FAQ responder already
built).
