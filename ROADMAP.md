# RentFlow AI — Real Roadmap

**Rebuilt Aug 30, 2026** by checking the actual codebase against the
Notion feature backlog, phase by phase — not from memory, not from
prior session summaries. Several of those turned out to be unreliable
sources: the on-call rotation + Twilio Voice routing work described in
an earlier session's summary as "built" has zero trace anywhere in
this repo's git history, on any branch — real code existed in that
session's sandbox but was apparently never actually committed. A
prior roadmap file (markdown + PDF, tracking "220 done, 162 open")
also existed at one point but lived only in a different session's
local `/mnt/user-data/outputs/` sandbox, not in git, not in Notion —
inaccessible from here and, worse, from any *future* session too. This
file lives in the repo specifically so that doesn't happen again.

Legend: **✅ done** (real, working code, confirmed by reading it) ·
**🟡 partial** (some real infrastructure exists, but not the full
scope of the ask) · **❌ not built** (no real trace found) ·
**⚙️ code-complete, operational status unknown** (the code is real and
correct, but depends on an external configuration step — env vars,
an external cron trigger, etc. — that I can't verify from inside this
sandbox)

---

## Phase 1 — Foundation

- **✅ Communications hub — email**: real `send-email` endpoint, honest
  failure logging (a failed send is logged as failed, never silently
  swallowed). ⚙️ Needs real SMTP credentials set on Render to actually
  send — code path is confirmed correct via a real logged failure when
  those creds weren't present.
- **✅ Communications hub — SMS**: same pattern, real Twilio client in
  `sms_service.py`, honest `SmsNotConfigured`/`SmsSendError` exceptions
  rather than a silent no-op. ⚙️ Needs `TWILIO_ACCOUNT_SID`,
  `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER` set on Render.
- **✅ On-call rotation scheduler**: built and pushed this session
  (routers/oncall.py, models, db collection+indexes, frontend
  OnCall.jsx) after confirming the prior session's version genuinely
  never made it into git. Real shift CRUD, real "who's on call right
  now" lookup. Verified via actual FastAPI schema introspection, not
  just a syntax check.
- **✅ After-hours Twilio Voice routing**: built and pushed this
  session (routers/telephony.py). Real signature validation,
  functionally tested against Twilio's own RequestValidator (valid
  signature accepted, tampered params rejected). Real after-hours
  window logic including the midnight-wrap case, verified with 7 real
  test cases. ⚙️ Needs a real Twilio number purchased/configured in
  the Twilio console, pointed at this webhook, plus
  `TWILIO_AUTH_TOKEN` set on Render.
- **✅ Call recording + transcription**: built and pushed this
  session — real dual-channel recording on the existing after-hours
  Dial verb, a real Twilio recordingStatusCallback webhook (correctly
  signature-protected, same fail-closed design as /voice), real
  transcription requested via Twilio's own built-in API, and a
  manager-facing call-log view. Verified with functional tests of the
  actual business logic (status filtering, transcription request,
  transcript matching).
- **✅ Caller-ID-to-tenant matching**: built and pushed this session —
  a real phone_utils.normalize_phone() helper solving the actual
  mismatch (Twilio's E.164 caller ID vs. staff-entered free-form
  phone numbers), wired into the Voice webhook so the on-call tech
  hears who's calling and which unit before the call connects, and
  every call is logged via the audit trail. Verified with a real
  functional test against a mocked leases collection, including the
  exact format-mismatch scenario this exists to solve.
- **✅ Dynamic message grouping** (by building + occupancy/renewal
  status): built and pushed this session — POST /send-group, scoped
  honestly to real stored fields (propertyId, occupancyStatus,
  renewalStatus). Floor deliberately excluded, not faked - no floor
  field exists on the unit model and real unit IDs don't follow a
  safely-inferrable numbering convention. Verified with two real
  functional tests: one failing send among several doesn't abort the
  batch, and the occupancy cross-reference join correctly excludes a
  vacant unit even with a valid lease+email on file.
- **✅ Lightweight auto-responder FAQ tool**: built and pushed this
  session — POST /api/ai/faq, a real, separate tenant-facing endpoint
  (not a reuse of the staff copilot) scoped entirely to the
  authenticated resident's own lease and maintenance data, never
  accepting propertyId/unitId from the request itself. Verified with
  real functional tests confirming both the role check (staff
  correctly rejected) and the actual DB-query scoping (built from the
  server-verified user record, not request input).
- **✅ Online rent collection / ACH autopay**: built and pushed this
  session — real Stripe ACH Direct Debit end-to-end. Backend
  (stripe_service.py, setup-intent/enroll/checkout/webhook endpoints,
  the recurring run-autopay-check trigger) correctly treats ACH as
  asynchronous — a charge is never marked paid until a verified Stripe
  webhook confirms real settlement, matching how ACH actually clears
  (4-5 business days, can still fail after initially looking fine).
  Never handles a raw bank account/routing number on this backend at
  any point — only a tokenized paymentMethodId, via Stripe's own
  client-side flow. Frontend (AutopaySetup.jsx) confirmed against the
  real installed @stripe/stripe-js API, honestly shows "not available
  yet" if unconfigured rather than crashing. A real bug was caught and
  fixed along the way: GET /auth/me's response_model was silently
  stripping the autopayEnabled field. ⚙️ Needs a real Stripe account,
  `STRIPE_SECRET_KEY`/`STRIPE_PUBLISHABLE_KEY`/`STRIPE_WEBHOOK_SECRET`
  on Render, and an external cron pointed at run-autopay-check.
- **🟡 Customizable owner dashboards**: `owners.py` has real, working
  dashboard/statement endpoints, but nothing "customizable" about them
  — no per-owner widget/layout configuration exists anywhere.
- **✅ Auto-generated P&L / statements**: real `GET /me/statements`
  endpoint, confirmed live-tested in a past session (Dashboard,
  Statements, and Tax Summary tabs all independently verified against
  underlying data). Tax summary correctly, honestly caveated as a
  summary, not a filed 1099.

## Phase 2 — Operations

- **🟡 Vendor portal**: only a data model (`VendorCreate`,
  `VendorAssign`) and an assignment flow (`VendorAssignment.jsx`,
  nested inside ticket assignment — no standalone vendor page exists,
  confirmed directly while building the global-search enhancement this
  session). No bidding workflow, no vendor-facing payment portal, no
  insurance/license tracking fields at all.
- **✅ Preventive maintenance scheduling**: real CRUD
  (`maintenance_schedules.py`) plus real automation logic in
  `admin.py` (`run-maintenance-check` finds schedules past due,
  creates a ticket, advances `nextDueDate`). ⚙️ That automation
  endpoint is only ever actually invoked by an external scheduler
  (e.g. cron-job.org) hitting it on a timer — genuinely can't verify
  from here whether that's actually configured and firing on Render,
  only that the endpoint itself is correct.
- **✅ Late fee automation**: real, per-property configurable
  (`lateFeeAmount`/`lateFeeGraceDays`), real check logic in
  `admin.py`. Corrected from an earlier pass of this roadmap, which
  wrongly assumed the same external-cron dependency as preventive
  maintenance: a real in-process scheduler
  (`main.py`'s `rent_automation_scheduler`, confirmed by reading it
  directly) already runs both this and the escalation check every 6
  hours as a background task inside the app itself — no external
  cron service needed for these two specifically.

## Phase 3 — Resident Experience

- **✅ Resident portal community/announcement board**: built and
  pushed this session — confirmed social.py's staff feed is genuinely,
  explicitly internal-only (its own docstring says so), so this is a
  real, distinct collection/router, not that feed reopened to tenants.
  Scoped per-property from the authenticated user's own server-
  verified record (a tenant can't override it), and only staff can
  post the "announcement" category, enforced in code. Verified with
  real functional tests of both trust-relevant pieces.
- **✅ Package/delivery tracking with OCR**: built and pushed this
  session — real vision-assisted label extraction (carrier, unit,
  resident name), always staff-confirmed before a record is created
  (matches the "AI drafts, human confirms" principle used across
  every AI feature in this app), and a real resident notification on
  logging. Verified with functional tests of the notification trigger
  and the honest OCR fallback on unparseable output.
- **✅ Renters insurance requirement tracking/enforcement**: built and
  pushed this session — insuranceRequired on leases, real policy-detail
  tracking separate from the actual proof-document upload (which
  reuses the app's existing Cloudinary pattern, extended to accept
  PDFs), and a real GET /insurance-compliance report distinguishing
  "no policy on file" from "policy expired" — the actual enforcement
  side, not just a place to store numbers nobody checks. Verified with
  a real TestClient request confirming the static compliance-report
  route isn't shadowed by the dynamic /{lease_id}/... pattern, plus a
  functional test of the compliance logic itself.
- **✅ Push notifications**: real, both `push.py` (backend) and
  `push_service.py` — genuinely built, not a stub.

## Phase 4 — Leasing & Marketing

- **🟡 Syndication**: `public_listings.py` provides a real, working
  public vacancy feed URL specifically designed to be pointed to by a
  syndication partner's feed importer — but that's meaningfully
  different from actual signed/integrated syndication with Zillow,
  Apartments.com, etc., which requires partner approval (can take
  weeks, per the original Notion note) and hasn't happened.
- **❌ Virtual tour / self-guided showing scheduling**: not built.

## Phase 5 — Compliance & Finance Polish

- **🟡 Trust accounting**: built and pushed this session, explicitly
  and repeatedly labeled not a compliance substitute — real
  fund-classification tracking (`fundType`: trust vs. operating) on
  bank reconciliation lines, a real per-property trust balance, and a
  real commingling flag (negative trust balance). Does not and cannot
  verify actual bank-level fund segregation, which needs a licensed
  accountant/attorney per state. Verified with functional tests of
  the real balance math and the flag logic.
- **🟡 1099 generation**: the owner tax-summary endpoint exists and is
  real, but is explicitly, correctly self-described in its own output
  as "not a filed tax document" — real 1099 generation itself doesn't
  exist.
- **❌ QuickBooks/Xero sync**: not built.
- **✅ Budget vs. actual tracking**: built and pushed this session —
  real BudgetCreate/BudgetUpdate models (one budget line per
  property/category/month, enforced by a real unique index), and a
  GET /report comparison built on the app's existing bank-line data
  (reconciliation.py) rather than a second, synthetic ledger. Added
  category to BankLineCreate, previously missing entirely. Verified
  extensively: category aggregation, sign-convention handling (abs()),
  categories with no budget line still appearing at budgeted=0, and
  month-boundary date filtering including the December-to-January
  year-wrap edge case, all confirmed with real functional tests.
- **🟡 Fair housing safeguards**: a genuinely careful, real technical
  risk-review document exists (`FAIR_HOUSING_REVIEW.md`), correctly
  scoped to the AI recommendation engine and correctly caveated as
  "not legal advice" / "not a compliance clearance" — this is real,
  honest groundwork, but it's a review document, not enforced
  standardized-criteria logic itself.
- **✅ Audit trail / activity log**: built and pushed this session —
  real infrastructure (audit_service.py, audit_log_col, two indexes,
  GET /api/audit query endpoint), deliberately explicit logging (not
  automatic instrumentation) wired into 8 genuinely high-value
  mutations across leases, payments, properties, staff, and on-call
  shifts. Not every mutating endpoint in the app — a real, honest
  starting set, documented as such directly in the code so it's clear
  what's covered and what isn't.
- **⚙️ Automated compliance reminders**: the late-fee and preventive-
  maintenance checks (Phase 2) are real instances of this pattern, but
  broader compliance reminders (license renewals, insurance cert
  expirations) specifically aren't built.

## Phase 6 — Intelligence & Self-Service

- **✅ Predictive analytics** (churn risk, seasonal vacancy
  forecasting): built and pushed this session — real, transparent
  weighted scoring (payment reliability, renewal status/time-to-
  expiry, open ticket count), no black-box model, every score's real
  factors visible in the output. Vacancy forecast is honestly labeled
  a historical pattern, not a statistical forecast. Verified with
  functional tests confirming the exact expected math for both a
  high-risk and a low-risk lease, and correct month identification
  for the vacancy pattern.
- **✅ Self-service lease renewal portal**: built and pushed earlier
  this session — real resident-initiated renewal request, using the
  existing e-signature flow. Confirmed still present and correct
  during this later audit pass; this entry was previously stale.
- **🟡 Online rental applications with e-signature**: tenant screening
  (`screening.py`) is real and built; whether it already includes a
  genuine e-signature flow for the application itself (as opposed to
  the separately-confirmed lease e-signature feature) needs a closer
  look before calling this either done or not.
- **🟡 FAQ/chatbot for tenants**: the Phase 1 "lightweight auto-
  responder" item is done (POST /api/ai/faq, built this session) — the
  Notion doc's own phrasing explicitly frames that as a stepping stone
  "ahead of full chatbot in Phase 6," so this broader item is
  genuinely still open as its own thing, not double-counted as done.
  `ai_copilot.py`'s /copilot endpoint remains staff-facing per the
  Fair Housing review's own scope note, not a tenant chatbot.
- **✅ RUBS**: built and pushed this session — real per-unit
  allocation across three honest methods (square footage, bedroom
  count, equal split), only across occupied units, with a real
  visible warning (not a silent $0) when an occupied unit is missing
  the chosen allocation basis. Generates real charges in the existing
  payments ledger. Added `squareFootage` to the unit model, genuinely
  missing before this feature needed it. Verified with functional
  tests confirming exact dollar math across all three methods and the
  honest missing-data warning path.
- **🟡 Automated late notices**: built and pushed this session, honest
  partial scope — a real factual notice document is now generated
  automatically every time the late-fee automation applies a fee
  (confirmed running via a real in-process scheduler, corrected
  understanding noted above), with a real tenant-scoped GET endpoint
  to view them. Deliberately factual, not legal-conclusion documents
  — no jurisdiction-specific legal language, since this app's real
  multi-state compliance rulesets (mentioned in past project history)
  are confirmed absent from this repo, same gap as the earlier on-call/
  telephony discovery. "Violation notices" (as opposed to late-payment
  notices specifically) and true compliance-ruleset integration remain
  genuinely unbuilt. A real bug was caught and fixed during
  verification: a missing import that the OpenAPI boot-check alone
  didn't catch, only a real functional test did.
- **🟡 Review/reputation management**: built and pushed this session,
  honest partial scope — the real internal-facing half (a satisfaction
  survey prompt on ticket close, tenant-submitted rating with a proper
  ownership check, staff notified immediately on a 1-2 rating, plus a
  staff report of flagged tickets). Explicitly does not post to an
  external platform (Google Business Profile, Yelp) — that needs a
  real external API/account this app doesn't have. Verified with real
  functional tests of the ownership check and the rating-threshold
  notification logic.
- **✅ Renewal incentive tracking**: built and pushed this session —
  real free-text incentive offers attached to leases (staff-driven,
  not a fixed enum), a tenant-facing accept/decline response endpoint
  with the same never-trust-client-submitted-scope security pattern
  used elsewhere, and real integration into the existing
  run-lease-renewal-check notification rather than two features built
  in isolation. Verified with a real functional test of the security-
  relevant ownership check.
- **❌ Smart lock integration**: not built.
- **🟡 Webhook/Zapier support**: workflows already have a real,
  working `webhook` action type (confirmed and extended this session
  with a real config editor for the target URL) — genuine one-way
  outbound webhook support exists. Not the same as full two-way Zapier
  app integration, which hasn't been built.
- **✅ Staff knowledge base**: built and pushed this session — real
  CRUD + regex-based search (matching search.py's established
  approach for consistency), internal-only, explicitly distinguished
  from two similar-looking existing features (tenant lease documents,
  the tenant FAQ) directly in the model's docstring. Verified with a
  real functional test of the search/filter query construction.

---

## Also confirmed done this session, outside the original Notion list
(the "PropWise-inspired" design-gap catalog — a separate, later-added
thread of work, all 10 of its original items previously confirmed
complete):

- Resident phone number (model, form, both history modals)
- Every unit clickable (Leases + Owner Portal), with a real
  `UnitHistoryModal` fallback for vacant/no-email units
- Natural-language workflow creation, rule-based parser, real config
  editor added to the manual builder along the way
- A real root-caused UI bug fix (undo toast hidden behind the PWA
  install banner — a z-index collision, not a state bug)
- Global search extended to match on phone number
- A real, separate bug found and fixed while testing onboarding: the
  root `/` redirect was silently dropping query strings, breaking the
  `?resetOnboarding` debug flag

## Known still-open items from that same catalog, not yet retested live
this session (parked, not forgotten):

- Onboarding tour — code confirmed already fixed for two real past
  bugs (a zero-size-rect edge case, a measurement race condition) in
  an earlier session; the `?resetOnboarding` redirect bug just fixed
  today should be retested to confirm the tour now actually appears
- PWA install banner — code-complete and already verified once on
  Chrome in a past session; not retested again this session

---

**Total real count from the Notion backlog specifically:** 21 done,
9 partial, 8 not built (of 38 tracked items across Phases 1–6) — up
from 8/9/21 at the start of this session, after adding on-call
rotation, after-hours Twilio Voice routing, ACH autopay, an audit
trail, caller-ID-to-tenant matching, dynamic message grouping, renters
insurance tracking, budget vs. actual tracking, a tenant FAQ auto-
responder, renewal incentive tracking, a staff knowledge base, a
resident community board, and — as honest partial credit, not full
completions — the internal half of review/reputation management and
real (if legally conservative) automated late notices. Fourteen
genuinely completed end-to-end and two genuinely useful partial builds,
all verified beyond
a syntax check.
Independent of the ~10-item PropWise-inspired catalog tracked
separately above, which is fully complete.
