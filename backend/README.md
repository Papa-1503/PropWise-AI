# RentFlow AI — local setup

## Backend

```bash
cd backend
python -m venv venv && source venv/bin/activate   # or your preferred env tool
pip install -r requirements.txt

cp .env.example .env
# then edit .env: set JWT_SECRET and ANTHROPIC_API_KEY

# make sure MongoDB is running locally, or point MONGO_URL at your instance

# seed a staff + tenant account for testing
python -m scripts.seed_users

# run the API
uvicorn main:app --reload --port 8000
```

Check it's up: `curl http://localhost:8000/api/health` → `{"status":"ok"}`

## Frontend

Drop the files in `frontend/` into your existing Vite + React app's
`src/` directory (or adjust import paths to match your structure). Wrap
your root render in `<AuthProvider>` — `App.jsx` already does this if
you use it as your top-level component.

Make sure your Vite dev server proxies `/api` to the backend, e.g. in
`vite.config.js`:

```js
export default {
  server: {
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
};
```

## Test accounts (from seed_users.py)

| Role   | Email                  | Password  |
|--------|-------------------------|-----------|
| Staff  | staff@rentflow.demo     | demo1234  |
| Tenant | tenant@rentflow.demo    | demo1234  |

## Known gaps to close before this is production-ready

- No data yet in `properties` / `leases` collections — the dashboard and
  AI copilot will show zeros/empty until you seed or create some via the
  API (`POST /api/properties`, `POST /api/leases`).
- Photo storage is local disk (`UPLOAD_DIR`) — fine for dev, swap for S3
  or similar before deploying anywhere with ephemeral storage.
- CORS in `main.py` is hardcoded to `http://localhost:5173` — update for
  your actual frontend origin(s) in production.
- No password reset / email verification flow yet.
- `properties` schema assumes embedded `units` arrays — confirm this
  matches your actual Mongo documents before relying on the dashboard
  math or the AI copilot's vacancy lookups.
- AI Action execution: **renewal campaigns and collections reminders now
  send real emails** via SMTP (see `email_service.py`) once you set
  `SMTP_HOST`/`SMTP_USER`/`SMTP_PASSWORD`/`FROM_EMAIL` in `.env`. Test
  your config with `POST /api/email/test-send?to=you@example.com` before
  trusting it in a real campaign. Rent adjustments and maintenance
  follow-ups are still stubbed — see `EXECUTORS` in `routers/ai_actions.py`.
- `LeasingAI` stats in `/api/dashboard/workforce` still report `null`/"not
  tracked" — there's no leads/tours/applications CRM wired up. `CollectionsAI`
  is now real, computed from the `payments` ledger.
- **Payments is a ledger, not a processor.** `routers/payments.py` tracks
  charges and manually-recorded payments — it does not move money. Wire
  a real processor (Stripe, etc.) behind `record_payment` if you want
  actual transactions instead of staff manually recording what came in.
- **Fair housing:** see `FAIR_HOUSING_REVIEW.md` before using `rent_adjustment`
  or any pricing-related AI action on real residents. This is a technical
  review, not a legal clearance.
- Vendor `distanceMiles` / `avgArrivalHours` are manually maintained
  fields, not a live geocoded ETA.
- Maintenance trend detection (`/api/dashboard/maintenance-trends`)
  needs real ticket volume and the `category` field populated on tickets
  to say anything meaningful — with only a handful of seeded tickets it
  won't surface any trends, which is correct behavior, not a bug.
## What has actually been run (and what hasn't)

This backend has been run for real against a live server process and
exercised with real HTTP requests (using an in-memory MongoDB-compatible
store as a stand-in for a real Mongo server, since none was available in
that environment — the code path is identical either way). This caught
and fixed five real bugs that static review had missed:

1. `main.py` crashed at startup — `StaticFiles` pointed at a folder that
   doesn't exist on a fresh checkout. Fixed: auto-created now.
2. **The documented startup command didn't work at all.** Every file used
   relative imports, which break when run the way the README instructs
   (`cd backend && uvicorn main:app`). Fixed: converted to absolute
   imports everywhere. Re-verified the exact documented command works.
3. `passlib` + current `bcrypt` are incompatible (a real, common
   ecosystem issue right now, not a hypothetical) — broke password
   hashing on first use. Fixed: dropped `passlib`, call `bcrypt` directly.
4. Naive vs. timezone-aware datetime comparison crashed the payments
   delinquency logic the first time it ran with a real overdue charge.
   Fixed with a shared `date_utils.py` helper.
5. `occupancy_insight` returned a raw MongoDB `ObjectId` in its response,
   which FastAPI can't serialize to JSON — crashed on first real call.
   Fixed: converted to a string.

**Verified working end-to-end with real requests:** registration/login
for both roles, JWT auth and role enforcement (tenant correctly blocked
from staff routes), property creation, dashboard health/occupancy math,
lease creation, the full payments/delinquency/payment-recording flow,
inspection creation, photo upload, **PDF report generation with a real
embedded photo**, vendor creation and ticket assignment, maintenance
ticket create/update, the workforce stats endpoint, and the full
maintenance-trend-detection → deterministic AI action pipeline.

**Not yet tested** (no Claude API key or SMTP credentials were available
in the testing environment): AI Actions generation, the AI Copilot chat,
AI photo vision analysis, and actual email sending. All three fail
cleanly with clear error messages when their credentials are missing
(verified) — but the success path with real credentials has not been
exercised. Test those specifically once you have your own
`ANTHROPIC_API_KEY` and SMTP credentials in place.

### Final pass (found by systematic re-scanning, not general use)

Two more real bugs, both serious, found by scanning every router file
for functions missing their `@router` decorator — a bug class introduced
by earlier `str_replace` edits during development, where inserting code
above a function occasionally clipped the decorator line above it
without raising any error, since Python doesn't require decorators.

1. **`POST /api/inspections/analyze-photo` (AI photo recognition) was
   completely unregistered** — the decorator was missing, so this route
   would 404 for every request despite the code behind it being correct
   and the frontend calling it correctly. Fixed and verified live.
2. **`PATCH /api/ai/actions/:id/decision` (the approve/reject/edit
   endpoint that `AIActionsPanel.jsx`'s buttons depend on) was also
   unregistered.** This is a core piece of the whole "agentic" workflow
   — every Approve/Reject/Edit button in the UI would have failed
   silently against a 404. Fixed and verified live for all three
   decision types (approve, reject, edit), including the audit-trail
   fields (`approvedBy`, `rejectedBy`, `decisionNote`) all populating
   correctly.

A frontend gap was also found and fixed in this pass:
`VendorAssignment.jsx` was fully built and its backend endpoint tested
working, but nothing in the UI ever rendered it — there was no button to
reach it. Added an "Assign vendor" / "Reassign vendor" toggle to each
maintenance ticket row in `MaintenanceTickets.jsx`.

**Lesson for future edits to this codebase:** after any `str_replace`
that inserts a new function or endpoint near existing ones, explicitly
grep for `@router\.(get|post|patch|delete)` immediately above every
`async def` in the file — Python's silence about a missing decorator
means this class of bug produces no error until the specific route is
actually called.

### Second final pass — a real security gap, not just crashes

A systematic audit of every single route across every router (checking
that each has `Depends(require_staff)` or `Depends(get_current_user)`
in its signature) found something more serious than a crash: **entire
routers had zero authentication on every endpoint**, meaning the data
was silently readable — and in some cases writable — by anyone, with
no token at all. This is worse than a 500 error because it fails
"successfully": the request just works, so nothing looks broken during
normal testing.

Found and fixed:

- **`dashboard.py` — all 5 endpoints unauthenticated**, including
  portfolio health (revenue at risk, delinquent balances, occupancy)
  and workforce stats. Anyone could read your portfolio's financials
  without logging in.
- **`properties.py` — all 5 endpoints unauthenticated**, including
  `POST` (create) and `PATCH` (update/change unit status). Anyone
  could create or modify property and unit records with zero auth.
- **`leases.py` — all 3 endpoints unauthenticated**, including create
  and update. Lease data includes resident names, emails, and rent —
  and it was both fully readable and fully writable with no token.
- **`ai_copilot.py` — the chat endpoint had no auth at all.** Fixed
  with `get_current_user` (not `require_staff`) since both staff and
  tenants legitimately use this feature — a stricter check would have
  broken the tenant portal.
- **`inspections.py` — `get_inspection` and `list_inspections`
  (the two GET endpoints) had no auth**, while every other endpoint in
  the same file correctly required staff. Fixed to match.

All fixes were verified live: confirmed each endpoint now correctly
returns 401 with no token, and confirmed normal authenticated use still
works identically to before.

**Root cause, for what it's worth:** these routers were each written in
separate turns across the conversation, and the auth pattern was applied
inconsistently — some routers got it by default, others were missed
entirely. This is exactly the kind of gap that's invisible from reading
any single file in isolation (each individual function looks
reasonable) and only surfaces from a systematic cross-file audit or,
as happened here, from actually testing an endpoint with no token and
noticing it shouldn't have worked.

### Third pass — a privilege escalation bug, worse than the auth gaps

Found by testing what happens when someone tries to register with a
role they shouldn't have: **`POST /api/auth/register` passed the
client-supplied `role` field straight through to the database with zero
restriction.** Anyone could self-register with `{"role": "staff"}` in
the request body and instantly get a full staff account — meaning every
`require_staff` check added in the previous pass was trivially
bypassable by just asking for the staff role at signup. This is more
serious than the missing-auth bugs because it doesn't just leak data,
it hands out the keys.

**Fixed:** `/register` now hardcodes `role="tenant"` unconditionally —
whatever the client sends in that field is ignored. A new endpoint,
`POST /api/auth/register-staff`, requires an *existing* staff member's
token to create another staff account. Verified live: an attacker
requesting `role: "staff"` now gets silently downgraded to a tenant
account with no property/unit access, and a direct attempt to hit
`/register-staff` without a staff token correctly returns 403.

**This creates a real bootstrapping requirement worth knowing about:**
there is now no way to create the *first* staff account through the API
at all — `/register-staff` correctly requires a staff token to use it,
and none exist yet on a fresh database. This is intentional, not a bug.
`scripts/seed_users.py` solves this by inserting directly into MongoDB,
bypassing the API entirely — which is exactly what a seed/bootstrap
script is for. If you need to create additional staff accounts outside
of seeding, use `/register-staff` with an existing staff member's token,
not the public `/register` endpoint.

### Fourth pass — unit-claiming, input validation, and injection

**Unit-claiming vulnerability (found immediately after the role fix,
by thinking through what else `/register` still trusted from the
client):** even after locking down `role`, the public `/register`
endpoint still let a client supply *any* `propertyId`/`unitId` with zero
verification. Confirmed live: two different people were able to
simultaneously self-register claiming the same unit, and both got 200 OK
access to that unit's payment data. Fixed: `propertyId`/`unitId` are now
only attached to a new account if a matching lease already exists (staff
creates the lease first) with `residentEmail` equal to the registering
email. Otherwise the account is still created — registration doesn't
fail — but with no unit binding, so it has no access to anyone's data
until a real lease ties it to a real unit. Verified live: an account
with a genuinely matching lease gets bound correctly; one without a
lease, or with a different email than the lease, gets nulled out.
(Note: this testing needed FastAPI's `TestClient` instead of separate
server processes — the earlier cross-process mongomock issue silently
produced a false negative on the first attempt, worth remembering for
any future testing in this kind of sandboxed environment.)

**Input validation gaps:**
- `ChargeCreate.amountDue` and `PaymentRecord.amountPaid` had no
  positivity constraint — a `-$500` "charge" was accepted and stored
  successfully. Fixed with `Field(gt=0)`.
- `LeaseCreate.rent`, `UnitIn.rent`/`bedrooms`, and `VendorCreate.baseCost`
  had no non-negative constraint. Fixed with `Field(ge=0)`.
- `VendorCreate.rating` already had `ge=0, le=5` and correctly rejected
  an out-of-range value (99) with a clean 422 — no fix needed, confirmed
  working as designed.

**Crash → clean error:** a malformed date string (e.g. `"not-a-date"`)
sent to any endpoint that parses a date raised an uncaught `ValueError`,
producing a raw unhandled 500. Fixed in the shared `date_utils.py`
helper (one fix point covers every call site) to catch this and return
a proper `400` with a clear message instead.

**Checked and found NOT vulnerable:**
- **NoSQL operator injection** (e.g. `{"email": {"$ne": null}}` to bypass
  a login check) — Pydantic's `str` type validation rejects dict-shaped
  input before it ever reaches a MongoDB query, on every tested endpoint.
  This class of attack is not exploitable here.
- **Stack trace leakage** — `debug` is never set to `True` anywhere, so
  FastAPI/Starlette's default (no traceback in the response body on an
  unhandled exception) applies. Confirmed by inspection.
- Diagnostic error messages that include raw exception text (Claude API
  errors, SMTP errors) are only ever visible to already-authenticated
  staff, and are useful for debugging their own environment
  configuration — left as-is deliberately rather than "fixed."

### Fifth pass — file upload validation and PDF generation crashes

**Stored XSS via file upload, confirmed live:** the actual photo-upload
endpoint (`upload_inspection_photo` / `save_photo_file`) had zero
content-type validation — unlike `analyze-photo`, which already checked
correctly. An HTML file with an embedded `<script>` tag was uploaded
through the "photo" endpoint, saved with a `.html` extension (taken
directly from the client-supplied filename), and served back by the
`/uploads` static mount with `content-type: text/html` — meaning it
would execute as a live page from the app's own origin. Fixed: the
saved file extension is now derived from a server-validated,
allowlisted content-type, never from the client-supplied filename, so
an upload can only ever be saved as a genuine image type.

**PDF generation crash #1 — unescaped user text breaks the markup
parser:** ReportLab's `Paragraph()` interprets its input as a small
HTML-like markup language. Every dynamic value that reached a
`Paragraph` (uploaded filename, inspector name, room name, unit/property
ID) was unescaped. Confirmed live: a photo uploaded with the filename
`test<font color="red">evil.jpg` crashed the **entire PDF report** with
an unhandled exception — not just that one photo's caption, the whole
document failed to build. Fixed with a shared `_pdf_text()` escaping
helper applied to every dynamic value before it enters an f-string
passed to `Paragraph()`.

**PDF generation crash #2 — a `try/except` that didn't actually work:**
the code wrapped `RLImage(local_path, ...)` construction in a
try/except intended to fall back to a text caption if an image file
couldn't be loaded. This never worked, because ReportLab's `Image`
flowable loads lazily — the file isn't actually read/decoded until
`doc.build()` runs, which is *after* the try/except has already exited
successfully. A corrupt or truncated image file (e.g. a failed upload)
would crash the whole PDF build regardless of the try/except. Confirmed
live with a "photo" upload whose bytes weren't valid image data. Fixed
by validating each image file explicitly with PIL *before* deciding
whether to add an `RLImage` or a fallback caption, rather than relying
on a try/except around the flowable's construction. Added `Pillow`
explicitly to `requirements.txt` since it's now imported directly
rather than relied on transitively through reportlab.

All four scenarios (malicious filename + valid image, corrupt image
data, non-image file type, and the original crash reproduction) were
re-tested together in one PDF generation call and confirmed to produce
a clean, valid PDF with no crash.

## New features: Notifications ("Notify") and Team Feed ("Workvivo")

Two additions, both live-tested the same way as everything else above.

**Notifications** (`notifications_service.py`, `routers/notifications.py`)
— a real in-app notification system, not a stub. Notifications are
always created server-side as a side effect of a real event; there's no
public "create notification" endpoint. Wired to four real triggers:
- Urgent maintenance ticket created → fans out to all staff
- Vendor assigned to a ticket → notifies that unit's tenant
- Payment recorded → notifies that unit's tenant
- New AI Actions generated → notifies all staff

`GET /api/notifications`, `/unread-count`, `PATCH /:id/read`,
`PATCH /read-all` — available to both staff and tenants (each only ever
sees their own). Frontend: `NotificationBell.jsx`, a bell icon in the
header with an unread badge and dropdown panel, polling every 30s.
Swap the polling for websockets/SSE if you want real push instead.

**Team Feed** (`routers/social.py`, staff-only — this is internal comms,
not resident-facing) — announcements, general posts, and peer
recognition ("shoutouts") with reactions and threaded comments. A
shoutout requires tagging a real colleague (`GET .../colleagues` backs
the picker) and fires them a real notification. Frontend: `SocialFeed.jsx`.

Verified live: notification fan-out to multiple staff, per-user read
scoping (one staff member can't mark another's notification read — 404,
not a silent no-op), shoutout-triggers-notification, reaction toggling,
comment threads with author-notification, and role enforcement (tenants
correctly blocked from the staff feed with 403, but share the
notification system; both correctly 401 with no token at all).

