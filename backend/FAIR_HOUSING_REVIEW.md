# Fair Housing Risk Review — AI Actions Engine

**Status:** Internal technical review only. **This is not legal advice** and
does not constitute a fair housing compliance clearance. Anything touching
pricing, unit selection, or resident treatment recommendations should be
reviewed by a qualified fair housing attorney before being used to make
real decisions about real residents or applicants. This document exists so
that review can start from an informed baseline instead of nothing.

**Scope:** `routers/ai_actions.py` (the recommendation/approval engine) and
`routers/ai_copilot.py` (the chat assistant), as of this review.

---

## 1. Why this matters here specifically

The Fair Housing Act (and most state/local equivalents) prohibits
discrimination in housing decisions based on race, color, national origin,
religion, sex, familial status, and disability — and several jurisdictions
add sexual orientation, gender identity, source of income, and other
protected classes. Liability can arise from:

- **Disparate treatment** — intentionally treating protected-class members
  differently.
- **Disparate impact** — a facially neutral policy or algorithm that
  produces a discriminatory effect in practice, *even without intent*.

An AI system that recommends which units get rent discounts, which
residents get priority outreach, or how "confident" a recommendation is —
is squarely the kind of system disparate-impact claims target, because the
algorithm's internal reasoning is often invisible to the people it affects.
HUD and DOJ have both signaled increased scrutiny of algorithmic
tenant-screening and pricing tools in recent years.

## 2. What data the engine has access to (as of this review)

| Data point | Used in `generate_actions` context? | Notes |
|---|---|---|
| Unit ID | Yes | Objective identifier |
| Rent amount | Yes | Objective |
| Lease dates / renewal status | Yes | Objective |
| Maintenance ticket volume/category | Yes | Objective |
| Vacancy status | Yes | Objective |
| **Resident name** | **No — removed in this review** | Previously included; stripped because it added no decision-relevant information and created risk (see §3) |
| Resident race/ethnicity/religion/etc. | **Not collected anywhere in this system** | There is no field for this in `models.py`, and there should never be one used for pricing/priority logic |
| Resident email | No (only used at send-time, after a decision is already made) | |
| Property address / geography | Yes, at the property level | See §4 — geographic proxies are a real risk even without explicit demographic data |

## 3. Specific risk found and fixed in this review

**Finding:** `gather_portfolio_context()` included resident names in the
same text block Claude used to decide each action's `priority` and
`confidence` score. Nothing instructed the model to use identity, but
names can carry inferable signals (e.g., apparent national origin) that a
language model can pick up on even without being asked to. Since the
model's *output* (which units get flagged, how urgently, how confidently)
directly affects who gets contacted and who gets a rent discount offer,
this was a real — if unintentional — disparate-treatment risk vector.

**Fix applied:** resident names are no longer included anywhere in the
context used to generate recommendations. Names are looked up fresh from
the database only after a human has already approved an action, at the
point of actually sending an email (see `execute_renewal_campaign` /
`execute_collections_reminder`). The system prompt was also updated with
an explicit instruction to base every recommendation only on objective
unit/lease/maintenance data and to apply identical criteria to every unit.

**What this does NOT resolve:** prompting a model not to discriminate is
not a substitute for testing whether its outputs are actually
non-discriminatory in practice. See §5.

## 4. Remaining risk vectors — not yet resolved

1. **Geographic/building proxies.** If certain buildings, floors, or
   property clusters correlate with protected-class concentration (a
   common real-world pattern), *any* recommendation logic that treats
   units differently by property/building — including the existing
   `rent_adjustment` and `maintenance-trends` features — can produce a
   disparate impact even with zero demographic data involved. This can't
   be fixed in code alone; it needs outcome monitoring (see §5).

2. **No outcome monitoring exists yet.** There is currently no mechanism
   to check, after the fact, whether approved rent adjustments, renewal
   priorities, or collections outreach ended up correlating with
   protected-class status across the resident population. Without this,
   nobody would notice a disparate impact even if one existed.

3. **Human approval is a safeguard, not a guarantee.** Every AI action
   requires a staff member to approve/reject/edit (`decide_action`), and
   this review adds an audit trail (`approvedBy`, `approvedAt`,
   `rejectedBy`, `decisionNote`) recording who made each call. This is
   necessary for defensibility but doesn't prevent a staff member from
   approving a biased suggestion, or from applying their own bias when
   choosing which suggestions to approve.

4. **`rent_adjustment` is the highest-risk action type** and is currently
   the least built-out (execution is still stubbed — see main README).
   Before this type is ever wired to actually change real rent, it should
   get the most scrutiny of any feature in this codebase: consistent,
   objective, documented criteria for every adjustment, applied uniformly.

5. **AI Copilot (`ai_copilot.py`) has broader data access** — it can
   surface resident names and lease details in answer to staff questions,
   which is appropriate for an internal tool answering "who hasn't
   renewed yet," but staff should be trained not to ask it
   discrimination-adjacent questions ("show me units with mostly X
   residents") and the system should not be extended to answer them if
   asked.

## 5. What a real clearance would require (recommended next steps)

- [ ] Attorney review of this document and the actual prompts/code, not
      just a summary of it.
- [ ] A documented, objective, written policy for when `rent_adjustment`
      actions are appropriate — independent of this AI system — that the
      AI is instructed to apply, so recommendations are auditable against
      a human-authored standard.
- [ ] Outcome monitoring: periodically check whether approved actions
      (rent adjustments, renewal priority, collections outreach) show any
      correlation with protected-class status, geography-as-proxy, or
      other suspect patterns, once there's enough real usage data to
      analyze.
- [ ] Staff training on both (a) not overriding AI suggestions in a
      discriminatory direction and (b) not using the copilot to ask
      discrimination-adjacent questions.
- [ ] A defined incident/complaint process if a resident or applicant
      alleges discriminatory treatment connected to an AI-approved action.
- [ ] Reconsider whether `rent_adjustment` should be AI-suggested at all
      versus a purely rules-based system with fixed, published criteria —
      a rules engine is often easier to defend than an LLM's reasoning,
      even a well-prompted one.

## 6. Changes made in this review (for the commit record)

1. Removed resident names from `gather_portfolio_context()`.
2. Added an explicit fair-housing constraint to the `generate_actions`
   system prompt.
3. Added `approvedBy` / `approvedAt` / `rejectedBy` / `rejectedAt` /
   `lastDecisionBy` fields to every AI action decision, for audit
   defensibility.

None of these changes constitute a compliance clearance on their own —
they close one identified code-level risk and add auditability. Items in
§5 remain outstanding.
