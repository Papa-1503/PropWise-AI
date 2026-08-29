/**
 * workflowParser
 *
 * Turns a plain-English sentence into a draft workflow (trigger +
 * actions) matching the exact shape WorkflowCreate expects on the
 * backend (see backend/models.py, backend/services/workflow_actions.py).
 *
 * Deliberately rule-based, not an LLM call: the trigger and action
 * vocabulary here is closed and small (6 triggers, 6 action types),
 * so a keyword/pattern matcher is deterministic, instant, free, and
 * — critically — can never hallucinate a trigger or action type that
 * doesn't exist in the automation engine. An LLM producing free-text
 * config values for a system that actually sends real emails and
 * creates real tickets is a correctness risk this doesn't need to
 * take on.
 *
 * This never creates a workflow directly — it only returns a parsed
 * draft for the UI to show the user for review/edit before they save,
 * since a misparsed automation (wrong trigger, wrong recipient) is a
 * real operational mistake, not a cosmetic one.
 */

const TRIGGER_PATTERNS = [
  { event: "lease_created", patterns: [/lease (?:is |gets )?(?:created|signed|starts)/i, /new lease/i, /when .*sign(?:s|ed)? a lease/i] },
  { event: "tenant_moved_out", patterns: [/tenant moves? out/i, /resident moves? out/i, /move[\s-]?out/i] },
  { event: "unit_created", patterns: [/unit (?:is |gets )?(?:created|added)/i, /new unit/i] },
  { event: "payment_received", patterns: [/payment (?:is |gets )?received/i, /rent (?:is |gets )?paid/i, /payment comes? in/i] },
  { event: "payment_returned", patterns: [/payment (?:is |gets )?returned/i, /payment bounces?/i, /nsf/i, /failed payment/i] },
  { event: "work_order_closed", patterns: [/work order (?:is |gets )?closed/i, /ticket (?:is |gets )?closed/i, /maintenance (?:is |gets )?(?:closed|completed|done)/i] },
];

const ACTION_PATTERNS = [
  { type: "send_email", patterns: [/send (?:an? )?(?:welcome )?email/i, /email (?:the|them|resident|tenant)/i] },
  { type: "create_turnover_checklist", patterns: [/turnover checklist/i, /turnover inspection/i] },
  { type: "create_task", patterns: [/create (?:a )?task/i, /create (?:a )?ticket/i, /open (?:a )?ticket/i] },
  { type: "assign_user", patterns: [/assign (?:a |the )?(?:user|tech|staff)/i, /assign (?:it |this )?to/i] },
  { type: "set_status", patterns: [/set (?:the )?status/i, /mark (?:it |as )?(?:as )?\w+/i] },
  { type: "webhook", patterns: [/call (?:a |the )?webhook/i, /webhook/i, /hit (?:a |the )?(?:url|endpoint)/i] },
];

// Pull a quoted or trailing phrase to use as a subject/title, e.g.
// `send a welcome email saying "Thanks for signing!"` or
// `send a welcome email` (falls back to a sensible default per action).
function extractQuoted(text) {
  const match = text.match(/["“]([^"”]+)["”]/);
  return match ? match[1] : null;
}

function extractUrl(text) {
  const match = text.match(/https?:\/\/\S+/);
  return match ? match[0] : null;
}

const ACTION_DEFAULTS = {
  send_email: () => ({ subject: "Notification from RentFlow AI", body: "" }),
  create_task: () => ({ title: "Automated task" }),
  create_turnover_checklist: () => ({}),
  assign_user: () => ({ userId: "" }),
  set_status: () => ({ status: "" }),
  webhook: () => ({ url: "" }),
};

/**
 * Parses one sentence into { trigger, actions, unmatched }.
 * `unmatched` is a list of clause fragments the parser couldn't map
 * to a known action — surfaced in the UI so the user knows to add
 * those manually rather than silently dropping intent.
 */
export function parseWorkflowSentence(sentence) {
  const text = sentence.trim();
  if (!text) return { trigger: null, actions: [], unmatched: [] };

  let trigger = null;
  for (const { event, patterns } of TRIGGER_PATTERNS) {
    if (patterns.some((p) => p.test(text))) {
      trigger = { event };
      break;
    }
  }

  // Split the sentence into action clauses on "and"/commas after the
  // trigger clause, so "send an email and create a turnover checklist"
  // becomes two clauses instead of one blob that only matches the
  // first pattern found.
  const clauses = text
    .split(/,| and /i)
    .map((c) => c.trim())
    .filter(Boolean);

  const actions = [];
  const unmatched = [];

  clauses.forEach((clause, i) => {
    // Skip the clause that only contains the trigger language itself
    // (e.g. "when a lease is created") so it isn't also treated as an
    // unmatched action clause.
    const isTriggerOnly = TRIGGER_PATTERNS.some(({ patterns }) => patterns.some((p) => p.test(clause)))
      && !ACTION_PATTERNS.some(({ patterns }) => patterns.some((p) => p.test(clause)));
    if (isTriggerOnly) return;

    const matchedAction = ACTION_PATTERNS.find(({ patterns }) => patterns.some((p) => p.test(clause)));
    if (!matchedAction) {
      unmatched.push(clause);
      return;
    }

    const config = ACTION_DEFAULTS[matchedAction.type]();
    const quoted = extractQuoted(clause);
    const url = extractUrl(clause);

    if (matchedAction.type === "send_email" && quoted) config.subject = quoted;
    if (matchedAction.type === "create_task" && quoted) config.title = quoted;
    if (matchedAction.type === "webhook" && url) config.url = url;
    if (matchedAction.type === "set_status") {
      // "set status to X" / "mark it as X" — pull the word after
      // to/as as the target status if present.
      const statusMatch = clause.match(/(?:to|as)\s+([a-z_-]+)/i);
      if (statusMatch) config.status = statusMatch[1];
    }

    actions.push({ type: matchedAction.type, config, order: actions.length + 1 });
  });

  return { trigger, actions, unmatched };
}
