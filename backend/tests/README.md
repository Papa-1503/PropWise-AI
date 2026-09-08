# Backend test suite

## Running locally

```bash
cd backend
pip install -r requirements.txt
pip install -r requirements-test.txt
python -m pytest tests/ -v
```

No real MongoDB, Stripe, or Anthropic credentials are needed — the
suite runs against an in-memory fake database (see `conftest.py`) and
never calls a real external API.

## What's covered

- **`test_multi_tenancy.py`** — the highest-value file here. Asserts
  that one organization can never see, list, or modify another
  organization's data, across a representative sample of endpoints
  (properties, leases, staff, custom roles, audit log, AI Actions).
- **`test_trial_enforcement.py`** — the real 14-day trial block:
  expired trials are blocked, paid/internal orgs never are, tenants
  are never affected by their landlord's billing state, and billing
  endpoints stay reachable even when blocked.
- **`test_billing.py`** — Stripe webhook signature verification (a
  forged event is rejected, a validly-signed one is accepted and
  actually updates the organization), and that only the real org
  owner can reach checkout/portal.
- **`test_auth.py`** — password verification, JWT requirement, and
  basic role enforcement.
- **`test_rate_limiting.py`** — proves the real login rate limiter
  actually works (disabled globally for every other test file so it
  doesn't make unrelated tests flaky — see `conftest.py`).
- **`test_schedulers_multi_org.py`** — the 8 background checks in
  `admin.py` (late fees, escalations, autopay, etc.) all loop per real
  organization since this session's rewrite; these tests call the
  real `_do_late_fee_check` and `_do_maintenance_check` functions
  directly (the same functions the real background scheduler calls)
  and confirm each organization's own settings and data stay
  genuinely isolated from the other's during a single run. Only 2 of
  the 8 checks are covered — see that file's own docstring for why
  the rest (Stripe/Twilio-dependent) aren't yet.

## A real gotcha worth knowing if you add tests here

`mongomock-motor` can return a collection wrapper via
`some_mock_db["name"]` that does not reliably share state with a
wrapper obtained by indexing the same name again later in the same
test — found the hard way while writing `test_schedulers_multi_org.py`.
For any test that needs to inspect a collection directly rather than
through the real HTTP API, import `db` and use its already-patched
reference (e.g. `db.tickets_col`) — the exact object the application
code itself reads and writes through — instead of re-indexing
`patch_db_with_mock["collection_name"]` fresh mid-test.

## What's NOT covered — stated honestly

This suite is real and passes against real application code (it
already caught one genuine bug — see `routers/billing.py`'s webhook
handler `.to_dict()` fix), but it is a starting point, not complete
coverage:

- Only a representative sample of the app's 60+ routers has
  multi-tenancy isolation tests. Extending coverage to more routers is
  real, valuable, ongoing work.
- Tests run against `mongomock-motor`, an in-memory fake of MongoDB's
  async API — not a full behavioral clone of real MongoDB. It does not
  perfectly replicate every aggregation pipeline operator or edge
  case. Testing against a real MongoDB instance before a major release
  is still worth doing separately.
- No tests exist yet for 6 of the 8 background scheduler checks in
  `admin.py` (escalations, autopay, lease renewal, payment reminders,
  vendor SLA, vendor compliance — see `test_schedulers_multi_org.py`
  for the 2 that are covered), the AI-generation endpoints (these call
  the real Anthropic API and would need mocking to test meaningfully),
  or the frontend.
