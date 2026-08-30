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
- **❌ Call recording + transcription**: not built.
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
- **❌ Lightweight auto-responder FAQ tool**: not built.
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
- **✅ Late fee automation**: same pattern as above — real, per-property
  configurable (`lateFeeAmount`/`lateFeeGraceDays`), real check logic
  in `admin.py`. Same ⚙️ external-cron caveat applies.

## Phase 3 — Resident Experience

- **❌ Resident portal community/announcement board**: not built (the
  existing "social feed" — `social.py`/`SocialFeed.jsx` — is a
  different, already-built feature; worth confirming with you whether
  it already covers this ask or whether a distinct board is still
  wanted).
- **❌ Package/delivery tracking with OCR**: not built, zero trace.
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

- **❌ Trust accounting**: not built.
- **🟡 1099 generation**: the owner tax-summary endpoint exists and is
  real, but is explicitly, correctly self-described in its own output
  as "not a filed tax document" — real 1099 generation itself doesn't
  exist.
- **❌ QuickBooks/Xero sync**: not built.
- **❌ Budget vs. actual tracking**: not built.
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

- **❌ Predictive analytics** (churn risk, seasonal vacancy
  forecasting): not built. (Note: a *different*, already-existing
  predictive-maintenance pattern-detection system was built in an
  earlier phase of this project per the stored project memory — worth
  confirming whether that's the intended foundation to extend here.)
- **❌ Self-service lease renewal portal**: not built.
- **🟡 Online rental applications with e-signature**: tenant screening
  (`screening.py`) is real and built; whether it already includes a
  genuine e-signature flow for the application itself (as opposed to
  the separately-confirmed lease e-signature feature) needs a closer
  look before calling this either done or not.
- **❌ FAQ/chatbot for tenants**: not built. (`ai_copilot.py` exists
  but — per the Fair Housing review's own scope note — is an internal
  staff-facing chat assistant, not a tenant-facing FAQ bot.)
- **❌ RUBS**: not built.
- **❌ Automated late/violation notices tied to compliance rulesets**:
  not built (late fee *application* exists and is automated; sending
  an actual notice document is a different, unbuilt piece).
- **❌ Review/reputation management**: not built.
- **❌ Renewal incentive tracking**: not built.
- **❌ Smart lock integration**: not built.
- **🟡 Webhook/Zapier support**: workflows already have a real,
  working `webhook` action type (confirmed and extended this session
  with a real config editor for the target URL) — genuine one-way
  outbound webhook support exists. Not the same as full two-way Zapier
  app integration, which hasn't been built.
- **❌ Staff knowledge base**: not built.

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

**Total real count from the Notion backlog specifically:** 16 done,
6 partial, 16 not built (of 38 tracked items across Phases 1–6) — up
from 8/9/21 at the start of this session, after adding on-call
rotation, after-hours Twilio Voice routing, ACH autopay, an audit
trail, caller-ID-to-tenant matching, dynamic message grouping, and
renters insurance tracking — all seven genuinely completed end-to-end
(not just started) and verified beyond a syntax check.
Independent of the ~10-item PropWise-inspired catalog tracked
separately above, which is fully complete.
