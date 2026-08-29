import { useState, useEffect, useCallback } from "react";
import { useAuth } from "./AuthContext";
import EmptyState from "./EmptyState";
import { Zap, Plus, X, Sparkles } from "lucide-react";

import { API_BASE } from "./config";
import { parseWorkflowSentence } from "./workflowParser";

/**
 * Workflows
 *
 * Visual create/manage/publish interface for the workflow automation
 * engine (see backend/routers/workflows.py, backend/services/events.py).
 * Replaces manually crafting ReqBin calls to build workflows.
 *
 * Expected workflow shape from the API:
 * {
 *   id, name, status: "draft"|"published"|"paused",
 *   trigger: { event, conditions },
 *   actions: [{ type, config, order }],
 *   createdAt, updatedAt
 * }
 */

const TRIGGER_OPTIONS = [
  { value: "lease_created", label: "When a lease is created" },
  { value: "tenant_moved_out", label: "When a tenant moves out" },
  { value: "unit_created", label: "When a unit is created" },
  { value: "payment_received", label: "When a payment is received" },
  { value: "payment_returned", label: "When a payment is returned" },
  { value: "work_order_closed", label: "When a work order is closed" },
];

const ACTION_OPTIONS = [
  { value: "send_email", label: "Send an email" },
  { value: "create_task", label: "Create a task" },
  { value: "create_turnover_checklist", label: "Create turnover checklist" },
  { value: "assign_user", label: "Assign a user" },
  { value: "set_status", label: "Set status" },
  { value: "webhook", label: "Call a webhook" },
];

const STATUS_STYLE = {
  draft: "bg-slate-50 text-slate-600 border-slate-200",
  published: "bg-emerald-50 text-emerald-700 border-emerald-200",
  paused: "bg-amber-50 text-amber-700 border-amber-200",
};

function triggerLabel(event) {
  return TRIGGER_OPTIONS.find((t) => t.value === event)?.label || event;
}

function actionLabel(type) {
  return ACTION_OPTIONS.find((a) => a.value === type)?.label || type;
}

// Real config fields per action type, matching exactly what each
// handler in backend/services/workflow_actions.py actually reads
// (config.get("subject"/"body"/"title"/"userId"/"status"/"url")) —
// create_turnover_checklist takes no config at all, so it's omitted
// here rather than shown with nothing to fill in.
const ACTION_CONFIG_FIELDS = {
  send_email: [
    { key: "subject", label: "Subject", placeholder: "Notification from RentFlow AI" },
    { key: "body", label: "Body", placeholder: "" },
  ],
  create_task: [{ key: "title", label: "Task title", placeholder: "Automated task" }],
  assign_user: [{ key: "userId", label: "User ID", placeholder: "" }],
  set_status: [{ key: "status", label: "Status", placeholder: "" }],
  webhook: [{ key: "url", label: "Webhook URL", placeholder: "https://" }],
};

function ActionConfigFields({ action, onChange }) {
  const fields = ACTION_CONFIG_FIELDS[action.type];
  if (!fields) return null; // create_turnover_checklist needs no config
  return (
    <div className="flex flex-col gap-1.5 pl-1 pb-1">
      {fields.map((f) => (
        <input
          key={f.key}
          className="border border-slate-200 rounded-lg px-2 py-1 text-xs"
          placeholder={f.label + (f.placeholder ? ` (e.g. ${f.placeholder})` : "")}
          value={action.config?.[f.key] || ""}
          onChange={(e) => onChange(f.key, e.target.value)}
        />
      ))}
    </div>
  );
}

function WorkflowRow({ workflow, onPublish, onPause, onDelete }) {
  const [busy, setBusy] = useState(false);
  const [health, setHealth] = useState(null);
  const [showHealth, setShowHealth] = useState(false);
  const { authFetch } = useAuth();

  const run = async (fn) => {
    setBusy(true);
    await fn(workflow.id);
    setBusy(false);
  };

  async function toggleHealth() {
    if (showHealth) {
      setShowHealth(false);
      return;
    }
    setShowHealth(true);
    if (!health) {
      try {
        const res = await authFetch(`${API_BASE}/workflows/${workflow.id}/health`);
        if (res.ok) setHealth(await res.json());
      } catch {
        // leave health null — the UI below handles that as "couldn't load"
      }
    }
  }

  return (
    <div className="border-b border-slate-200 last:border-none py-3">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-medium">{workflow.name}</span>
            <span
              className={`text-[10px] font-mono uppercase px-2 py-0.5 rounded-full border ${STATUS_STYLE[workflow.status]}`}
            >
              {workflow.status}
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-0.5">{triggerLabel(workflow.trigger?.event)}</p>
          <p className="text-xs text-slate-400 mt-1">
            {(workflow.actions || []).length === 0
              ? "No actions configured"
              : workflow.actions.map((a) => actionLabel(a.type)).join(" → ")}
          </p>
          <button onClick={toggleHealth} className="text-[11px] text-indigo-700 hover:underline mt-1">
            {showHealth ? "Hide run history" : "View run history"}
          </button>
          {showHealth && (
            <div className="mt-2 bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-xs">
              {!health ? (
                <span className="text-slate-400">Loading…</span>
              ) : health.runCount === 0 ? (
                <span className="text-slate-400">This workflow hasn't run yet.</span>
              ) : (
                <div className="grid grid-cols-2 gap-x-4 gap-y-1">
                  <span className="text-slate-500">Total runs: <strong className="text-slate-700">{health.runCount}</strong></span>
                  <span className="text-slate-500">Completion rate: <strong className="text-emerald-600">{health.completionRate}%</strong></span>
                  <span className="text-slate-500">Exception rate: <strong className={health.exceptionRate > 0 ? "text-amber-600" : "text-slate-700"}>{health.exceptionRate}%</strong></span>
                  <span className="text-slate-500">Avg duration: <strong className="text-slate-700">{health.avgDurationMs}ms</strong></span>
                </div>
              )}
            </div>
          )}
        </div>
        <div className="flex gap-2 shrink-0">
          {workflow.status !== "published" && (
            <button
              disabled={busy}
              onClick={() => run(onPublish)}
              className="text-[11px] text-emerald-600 underline disabled:opacity-40"
            >
              Publish
            </button>
          )}
          {workflow.status === "published" && (
            <button
              disabled={busy}
              onClick={() => run(onPause)}
              className="text-[11px] text-amber-600 underline disabled:opacity-40"
            >
              Pause
            </button>
          )}
          <button
            disabled={busy}
            onClick={() => run(onDelete)}
            className="text-[11px] text-rose-600 underline disabled:opacity-40"
          >
            Delete
          </button>
        </div>
      </div>
    </div>
  );
}

function NewWorkflowForm({ onCreated, onCancel }) {
  const [name, setName] = useState("");
  const [triggerEvent, setTriggerEvent] = useState(TRIGGER_OPTIONS[0].value);
  const [actions, setActions] = useState([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [nlText, setNlText] = useState("");
  const [nlUnmatched, setNlUnmatched] = useState([]);
  const [nlApplied, setNlApplied] = useState(false);
  const { authFetch } = useAuth();

  function handleParseNl() {
    const { trigger, actions: parsedActions, unmatched } = parseWorkflowSentence(nlText);
    if (trigger) setTriggerEvent(trigger.event);
    if (parsedActions.length > 0) setActions(parsedActions);
    setNlUnmatched(unmatched);
    setNlApplied(true);
    if (!name.trim()) {
      // A reasonable default name so the user isn't blocked on typing
      // one manually, but it's just a starting point — still editable
      // in the field below like anything else here.
      setName(nlText.trim().slice(0, 60));
    }
  }

  function addAction() {
    setActions((prev) => [...prev, { type: "send_email", config: {}, order: prev.length + 1 }]);
  }

  function updateActionType(index, type) {
    setActions((prev) => prev.map((a, i) => (i === index ? { ...a, type, config: {} } : a)));
  }

  function updateActionConfig(index, key, value) {
    setActions((prev) => prev.map((a, i) => (i === index ? { ...a, config: { ...a.config, [key]: value } } : a)));
  }

  function removeAction(index) {
    setActions((prev) => prev.filter((_, i) => i !== index).map((a, i) => ({ ...a, order: i + 1 })));
  }

  async function handleSave() {
    if (!name.trim()) return;
    setSaving(true);
    setError(null);
    try {
      const res = await authFetch(`${API_BASE}/workflows`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: name.trim(),
          trigger: { event: triggerEvent },
          actions,
        }),
      });
      if (!res.ok) throw new Error(`Server returned ${res.status}`);
      const created = await res.json();
      onCreated(created);
    } catch (err) {
      setError(err.message || "Couldn't create workflow.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="border border-slate-200 rounded-xl p-4 mb-4 bg-slate-50/50">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold">New workflow</h3>
        <button onClick={onCancel} className="text-slate-400 hover:text-slate-600">
          <X size={16} />
        </button>
      </div>

      <div className="bg-indigo-50/60 border border-indigo-100 rounded-lg p-3 mb-3">
        <label htmlFor="nl-workflow-input" className="text-xs font-medium text-indigo-700 flex items-center gap-1 mb-1.5">
          <Sparkles size={12} /> Describe it in plain English (optional)
        </label>
        <div className="flex gap-2">
          <input
            id="nl-workflow-input"
            className="flex-1 border border-indigo-200 rounded-lg px-3 py-2 text-sm bg-white"
            placeholder='e.g. "When a lease is created, send a welcome email"'
            value={nlText}
            onChange={(e) => {
              setNlText(e.target.value);
              setNlApplied(false);
            }}
            onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), handleParseNl())}
          />
          <button
            onClick={handleParseNl}
            disabled={!nlText.trim()}
            className="text-sm bg-indigo-600 text-white px-3 py-2 rounded-lg disabled:opacity-40 shrink-0"
          >
            Parse
          </button>
        </div>
        {nlApplied && (
          <p className="text-xs text-indigo-600 mt-1.5">
            Filled in the fields below — review before saving.
          </p>
        )}
        {nlUnmatched.length > 0 && (
          <p className="text-xs text-amber-600 mt-1">
            Couldn't recognize: {nlUnmatched.map((u) => `"${u}"`).join(", ")} — add it manually below if needed.
          </p>
        )}
      </div>

      <input
        className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm mb-2"
        placeholder="Workflow name"
        value={name}
        onChange={(e) => setName(e.target.value)}
      />

      <select
        className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm mb-3"
        value={triggerEvent}
        onChange={(e) => setTriggerEvent(e.target.value)}
      >
        {TRIGGER_OPTIONS.map((t) => (
          <option key={t.value} value={t.value}>
            {t.label}
          </option>
        ))}
      </select>

      <div className="space-y-2 mb-3">
        {actions.map((action, i) => (
          <div key={i} className="border border-slate-100 rounded-lg p-2">
            <div className="flex items-center gap-2 mb-1.5">
              <select
                className="flex-1 border border-slate-200 rounded-lg px-2 py-1.5 text-sm"
                value={action.type}
                onChange={(e) => updateActionType(i, e.target.value)}
              >
                {ACTION_OPTIONS.map((a) => (
                  <option key={a.value} value={a.value}>
                    {a.label}
                  </option>
                ))}
              </select>
              <button onClick={() => removeAction(i)} className="text-rose-500 hover:text-rose-600">
                <X size={14} />
              </button>
            </div>
            <ActionConfigFields action={action} onChange={(key, value) => updateActionConfig(i, key, value)} />
          </div>
        ))}
        <button onClick={addAction} className="text-[11px] text-indigo-600 underline flex items-center gap-1">
          <Plus size={12} /> Add action
        </button>
      </div>

      {error && <p className="text-xs text-rose-600 mb-2">{error}</p>}

      <button
        onClick={handleSave}
        disabled={saving || !name.trim()}
        className="text-sm bg-gradient-to-r from-indigo-600 to-fuchsia-600 text-white px-4 py-1.5 rounded-lg disabled:opacity-40"
      >
        {saving ? "Saving…" : "Save workflow"}
      </button>
    </div>
  );
}

export default function Workflows() {
  const [workflows, setWorkflows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const { authFetch } = useAuth();

  const fetchWorkflows = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await authFetch(`${API_BASE}/workflows`);
      if (!res.ok) throw new Error(`Server returned ${res.status}`);
      const data = await res.json();
      setWorkflows(data.workflows || data);
    } catch (err) {
      setError(err.message || "Couldn't load workflows.");
    } finally {
      setLoading(false);
    }
  }, [authFetch]);

  useEffect(() => {
    fetchWorkflows();
  }, [fetchWorkflows]);

  function handleCreated(created) {
    setWorkflows((prev) => [created, ...prev]);
    setShowForm(false);
  }

  async function handlePublish(id) {
    setWorkflows((prev) => prev.map((w) => (w.id === id ? { ...w, status: "published" } : w)));
    try {
      const res = await authFetch(`${API_BASE}/workflows/${id}/publish`, { method: "POST" });
      if (!res.ok) throw new Error("Publish failed");
    } catch {
      fetchWorkflows();
    }
  }

  async function handlePause(id) {
    setWorkflows((prev) => prev.map((w) => (w.id === id ? { ...w, status: "paused" } : w)));
    try {
      const res = await authFetch(`${API_BASE}/workflows/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: "paused" }),
      });
      if (!res.ok) throw new Error("Pause failed");
    } catch {
      fetchWorkflows();
    }
  }

  async function handleDelete(id) {
    const prev = workflows;
    setWorkflows((cur) => cur.filter((w) => w.id !== id));
    try {
      const res = await authFetch(`${API_BASE}/workflows/${id}`, { method: "DELETE" });
      if (!res.ok) throw new Error("Delete failed");
    } catch {
      setWorkflows(prev);
    }
  }

  return (
    <div className="max-w-2xl mx-auto p-5 bg-white rounded-xl border border-slate-200">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold">Workflows</h2>
        {!showForm && (
          <button
            onClick={() => setShowForm(true)}
            className="text-sm bg-gradient-to-r from-indigo-600 to-fuchsia-600 text-white px-3 py-1.5 rounded-full flex items-center gap-1.5"
          >
            <Plus size={14} /> New workflow
          </button>
        )}
      </div>

      {showForm && <NewWorkflowForm onCreated={handleCreated} onCancel={() => setShowForm(false)} />}

      {loading && <p className="text-sm text-slate-400">Loading workflows…</p>}

      {error && (
        <div className="text-sm text-rose-600 bg-rose-50 border border-rose-200 rounded px-3 py-2 flex items-center justify-between">
          <span>{error}</span>
          <button onClick={fetchWorkflows} className="underline text-xs">
            Retry
          </button>
        </div>
      )}

      {!loading && !error && workflows.length === 0 && !showForm && (
        <EmptyState
          icon={Zap}
          title="No workflows yet"
          subtitle="Create one to automate what happens when a lease is created, a payment comes in, and more."
        />
      )}

      {!loading &&
        !error &&
        workflows.map((workflow) => (
          <WorkflowRow
            key={workflow.id}
            workflow={workflow}
            onPublish={handlePublish}
            onPause={handlePause}
            onDelete={handleDelete}
          />
        ))}
    </div>
  );
}
