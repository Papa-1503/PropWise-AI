import { useState, useEffect, useCallback, useMemo } from "react";
import { useAuth } from "./AuthContext";
import { API_BASE } from "./config";
import EmptyState from "./EmptyState";
import { Sparkles, ChevronDown, ChevronRight } from "lucide-react";
/**
 * AIActionsPanel
 *
 * Renders the "AI Recommended Actions" cards from the new dashboard design,
 * backed by the real /api/ai/actions engine — not canned examples.
 *
 * Confidence scores and projected outcomes shown here are Claude's
 * reasoned estimate from live portfolio data, not a statistically
 * validated model. The small disclosure line reflects that honestly —
 * don't remove it without building real historical modeling first.
 */



const PRIORITY_STYLE = {
  high: "border-rose-300 bg-rose-50",
  medium: "border-amber-300 bg-amber-50",
  low: "border-slate-200 bg-slate-50",
};
const PRIORITY_LABEL_STYLE = {
  high: "text-rose-700 bg-rose-100",
  medium: "text-amber-700 bg-amber-100",
  low: "text-slate-600 bg-slate-100",
};
const RISK_STYLE = {
  high: "text-rose-600",
  medium: "text-amber-600",
  low: "text-emerald-600",
};

function ConfidenceBar({ value }) {
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 bg-slate-200 rounded-full overflow-hidden">
        <div
          className="h-full bg-slate-900 rounded-full"
          style={{ width: `${value}%` }}
        />
      </div>
      <span className="text-xs font-mono text-slate-500 w-9">{value}%</span>
    </div>
  );
}

function ActionCard({ action, onDecide }) {
  const [expanded, setExpanded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editedTitle, setEditedTitle] = useState(action.title);

  const handleDecision = async (decision, extra = {}) => {
    setBusy(true);
    await onDecide(action.id, decision, extra);
    setBusy(false);
    setEditing(false);
  };

  return (
    <div className={`border rounded-xl p-4 ${PRIORITY_STYLE[action.priority]}`}>
      <div className="flex items-center justify-between gap-2 mb-1.5">
        <span className={`text-[10px] font-mono uppercase tracking-wide px-2 py-0.5 rounded-full ${PRIORITY_LABEL_STYLE[action.priority]}`}>
          {action.priority}
        </span>
        <span className="text-[10px] font-mono text-slate-400 capitalize">{action.status}</span>
      </div>

      {editing ? (
        <input
          value={editedTitle}
          onChange={(e) => setEditedTitle(e.target.value)}
          className="w-full text-sm font-semibold border border-slate-300 rounded px-2 py-1"
          autoFocus
        />
      ) : (
        <h3 className="text-sm font-semibold">{action.title}</h3>
      )}
      <p className="text-xs text-slate-600 mt-1">{action.projectedOutcome}</p>

      {/* Exception Desk framing (Priority 22): surface why this needs a
          human — risk level and estimated value both already existed in
          the data but were never actually shown here before today. */}
      {(action.riskLevel || action.estimatedValue != null) && (
        <div className="flex items-center gap-3 mt-1.5 text-[11px]">
          {action.riskLevel && (
            <span className={RISK_STYLE[action.riskLevel]}>
              {action.riskLevel} risk
            </span>
          )}
          {action.estimatedValue != null && (
            <span className="text-slate-500">
              Est. impact: ${action.estimatedValue.toLocaleString()}
            </span>
          )}
        </div>
      )}

      <button
        onClick={() => setExpanded((e) => !e)}
        className="text-[11px] text-slate-500 underline mt-2"
      >
        {expanded ? "Hide details" : "Why is this suggested?"}
      </button>

      {expanded && (
        <div className="mt-2 text-xs text-slate-600 bg-white/60 rounded-lg p-3 space-y-2">
          <p>{action.rationale}</p>
          {action.affectedUnitIds?.length > 0 && (
            <p className="font-mono text-[11px]">Units: {action.affectedUnitIds.join(", ")}</p>
          )}
          {action.plannedSteps?.length > 0 && (
            <ul className="space-y-1">
              {action.plannedSteps.map((s, i) => (
                <li key={i} className="flex items-start gap-1.5">
                  <span className="text-emerald-600 font-bold">✓</span>
                  <span>{s}</span>
                </li>
              ))}
            </ul>
          )}
          <ConfidenceBar value={action.confidence} />
          <p className="text-[10px] text-slate-400 italic">
            AI-estimated confidence based on current data, not a statistically validated forecast.
          </p>
        </div>
      )}

      {action.status === "suggested" && !editing && (
        <div className="flex gap-2 mt-3">
          <button
            onClick={() => handleDecision("approve")}
            disabled={busy}
            title="Executes this action now"
            className="text-xs font-semibold bg-slate-900 text-white px-3 py-1.5 rounded-lg disabled:opacity-50"
          >
            {busy ? "…" : "Approve"}
          </button>
          <button
            onClick={() => setEditing(true)}
            disabled={busy}
            title="Change the title before approving"
            className="text-xs font-semibold bg-white border border-slate-300 px-3 py-1.5 rounded-lg disabled:opacity-50"
          >
            Edit
          </button>
          <button
            onClick={() => handleDecision("reject")}
            disabled={busy}
            title="Dismisses this suggestion — no action taken"
            className="text-xs font-semibold bg-white border border-slate-300 px-3 py-1.5 rounded-lg disabled:opacity-50"
          >
            Reject
          </button>
        </div>
      )}

      {editing && (
        <div className="flex gap-2 mt-3">
          <button
            onClick={() => handleDecision("edit", { editedTitle })}
            disabled={busy}
            className="text-xs font-semibold bg-slate-900 text-white px-3 py-1.5 rounded-lg disabled:opacity-50"
          >
            Save
          </button>
          <button
            onClick={() => {
              setEditing(false);
              setEditedTitle(action.title);
            }}
            className="text-xs font-semibold bg-white border border-slate-300 px-3 py-1.5 rounded-lg"
          >
            Cancel
          </button>
        </div>
      )}

      {(action.approvedBy || action.rejectedBy) && (
        <p className="text-[10px] text-slate-400 mt-2">
          {action.approvedBy
            ? `Approved by ${action.approvedBy}${action.approvedAt ? ` on ${new Date(action.approvedAt).toLocaleString()}` : ""}`
            : `Rejected by ${action.rejectedBy}${action.rejectedAt ? ` on ${new Date(action.rejectedAt).toLocaleString()}` : ""}`}
        </p>
      )}

      {action.status === "completed" && action.executionResult?.note && (
        <p className="text-[11px] text-slate-500 mt-2 italic">{action.executionResult.note}</p>
      )}
    </div>
  );
}

function GroupedActionCard({ title, items, onDecide }) {
  const [expanded, setExpanded] = useState(false);
  const totalValue = items.reduce((sum, a) => sum + (a.estimatedValue || 0), 0);

  return (
    <div className="border border-slate-200 rounded-xl overflow-hidden">
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center justify-between gap-3 p-3.5 bg-slate-50 hover:bg-slate-100 text-left"
      >
        <div className="flex items-center gap-2 min-w-0">
          {expanded ? <ChevronDown size={14} className="text-slate-400 shrink-0" /> : <ChevronRight size={14} className="text-slate-400 shrink-0" />}
          <span className="text-sm font-semibold truncate">{title}</span>
          <span className="text-[11px] font-mono text-slate-400 shrink-0">×{items.length}</span>
        </div>
        {totalValue > 0 && (
          <span className="text-xs font-semibold text-slate-500 shrink-0">${totalValue.toLocaleString()} total</span>
        )}
      </button>
      {expanded && (
        <div className="p-3 space-y-3 bg-white">
          {items.map((a) => (
            <ActionCard key={a.id} action={a} onDecide={onDecide} />
          ))}
        </div>
      )}
    </div>
  );
}

export default function AIActionsPanel({ propertyId }) {
  const [actions, setActions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState(null);
  const [view, setView] = useState("pending"); // "pending" | "history"
  const { authFetch } = useAuth();

  const fetchActions = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (view === "pending") params.set("status", "suggested");
      if (propertyId) params.set("propertyId", propertyId);
      const res = await authFetch(`${API_BASE}/ai/actions?${params.toString()}`);
      if (!res.ok) throw new Error(`Server returned ${res.status}`);
      const data = await res.json();
      let list = data.actions || [];
      // History mode fetches every status (the backend only supports one
      // exact status filter at a time) — exclude "suggested" ones here
      // since those already show under Pending.
      if (view === "history") list = list.filter((a) => a.status !== "suggested");
      setActions(list);
    } catch (err) {
      setError(err.message || "Couldn't load AI actions.");
    } finally {
      setLoading(false);
    }
  }, [propertyId, view, authFetch]);

  useEffect(() => {
    fetchActions();
  }, [fetchActions]);

  async function handleGenerate() {
    setGenerating(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (propertyId) params.set("propertyId", propertyId);
      const res = await authFetch(`${API_BASE}/ai/actions/generate?${params.toString()}`, {
        method: "POST",
      });
      if (!res.ok) throw new Error(`Server returned ${res.status}`);
      await fetchActions();
    } catch (err) {
      setError(err.message || "Couldn't generate new recommendations.");
    } finally {
      setGenerating(false);
    }
  }

  async function handleDecide(actionId, decision, extra = {}) {
    if (decision === "edit") {
      // stays in the list — just update its title locally, then sync
      setActions((prev) =>
        prev.map((a) => (a.id === actionId ? { ...a, title: extra.editedTitle || a.title } : a))
      );
    } else {
      // approve/reject leave the "suggested" list
      setActions((prev) => prev.filter((a) => a.id !== actionId));
    }
    try {
      const res = await authFetch(`${API_BASE}/ai/actions/${actionId}/decision`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decision, ...extra }),
      });
      if (!res.ok) throw new Error("Update failed");
    } catch {
      fetchActions(); // roll back by refetching on failure
    }
  }

  // Same-title actions collapse into one card — grouping by exact title
  // match, matching the maintenance-ticket grouping pattern built
  // earlier. Only groups when 2+ actions genuinely share a title (a
  // real, observed case: multiple simultaneous escalations for one
  // resident on the same day, each a separate real charge but visually
  // identical otherwise). Groups apply to both pending and history —
  // a resident with 3 approved escalations shouldn't clutter history
  // any less than 3 pending ones would clutter the queue.
  const { groups, ungrouped } = useMemo(() => {
    const byTitle = new Map();
    for (const a of actions) {
      if (!byTitle.has(a.title)) byTitle.set(a.title, []);
      byTitle.get(a.title).push(a);
    }
    const groupList = [];
    const soloList = [];
    for (const [title, items] of byTitle) {
      if (items.length >= 2) groupList.push({ title, items });
      else soloList.push(items[0]);
    }
    return { groups: groupList, ungrouped: soloList };
  }, [actions]);

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-lg font-semibold">AI Recommended Actions</h2>
          <p className="text-xs text-slate-500">Reviewed and grounded in live portfolio data</p>
        </div>
        <button
          onClick={handleGenerate}
          disabled={generating}
          className="text-xs font-semibold bg-amber-500 disabled:bg-slate-300 text-white px-3 py-2 rounded-lg"
        >
          {generating ? "Analyzing…" : "Generate new recommendations"}
        </button>
      </div>

      <div className="flex bg-slate-100 rounded-lg p-1 mb-4 text-xs font-semibold w-fit">
        <button
          onClick={() => setView("pending")}
          className={`px-3 py-1 rounded-md ${view === "pending" ? "bg-white shadow-sm" : "text-slate-500"}`}
        >
          Pending
        </button>
        <button
          onClick={() => setView("history")}
          className={`px-3 py-1 rounded-md ${view === "history" ? "bg-white shadow-sm" : "text-slate-500"}`}
        >
          Decision History
        </button>
      </div>

      {loading && <p className="text-sm text-slate-400">Loading…</p>}
      {error && (
        <p className="text-xs text-rose-600 bg-rose-50 border border-rose-200 rounded px-3 py-2 mb-3">
          {error}
        </p>
      )}
    {!loading && actions.length === 0 && !error && (
        <EmptyState
          icon={Sparkles}
          title={view === "pending" ? "No pending recommendations" : "No decisions yet"}
          subtitle={view === "pending"
            ? 'Click "Generate new recommendations" to have AI analyze current data.'
            : "Approved and rejected recommendations will show up here as a decision history."}
        />
      )}

      <div className="space-y-3">
        {groups.map((g) => (
          <GroupedActionCard key={g.title} title={g.title} items={g.items} onDecide={handleDecide} />
        ))}
        {ungrouped.map((action) => (
          <ActionCard key={action.id} action={action} onDecide={handleDecide} />
        ))}
      </div>
    </div>
  );
}
