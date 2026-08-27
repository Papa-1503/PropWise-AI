import { useState, useEffect, useCallback, useId } from "react";
import { useAuth } from "./AuthContext";
import EmptyState from "./EmptyState";
import { Landmark, Plus, X, Link2, Link2Off } from "lucide-react";
import { API_BASE } from "./config";

/**
 * Reconciliation
 *
 * Priority 47 — manual bank-line-to-charge matching. No live bank feed
 * connected; staff enter statement lines and match them against real
 * charges already in the payments ledger. The backend already had a
 * genuinely useful "suggest matches" endpoint (same-amount, same-
 * property candidates) — built but unused until now.
 */

function NewLineModal({ propertyId, onClose, onSaved }) {
  const [date, setDate] = useState("");
  const [description, setDescription] = useState("");
  const [amount, setAmount] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const { authFetch } = useAuth();
  const idPrefix = useId();

  async function handleSave() {
    if (!date || !description.trim() || !amount) {
      setError("Date, description, and amount are all required.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const res = await authFetch(`${API_BASE}/reconciliation/lines`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ propertyId, date, description, amount: Number(amount) }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Something went wrong");
      onSaved();
      onClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-30 p-4">
      <div className="bg-white rounded-xl shadow-lg w-full max-w-md p-5">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-semibold">New bank statement line</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600">
            <X size={18} />
          </button>
        </div>

        <div className="space-y-3">
          <div>
            <label htmlFor={`${idPrefix}-date`} className="text-xs text-slate-500">Date</label>
            <input
              id={`${idPrefix}-date`}
              type="date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              className="w-full text-sm border border-slate-200 rounded px-2 py-1.5 mt-0.5"
            />
          </div>
          <div>
            <label htmlFor={`${idPrefix}-desc`} className="text-xs text-slate-500">Description (as shown on the bank statement)</label>
            <input
              id={`${idPrefix}-desc`}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="e.g. ACH DEPOSIT 104-SMITH"
              className="w-full text-sm border border-slate-200 rounded px-2 py-1.5 mt-0.5"
            />
          </div>
          <div>
            <label htmlFor={`${idPrefix}-amount`} className="text-xs text-slate-500">Amount</label>
            <input
              id={`${idPrefix}-amount`}
              type="number"
              step="0.01"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              className="w-full text-sm border border-slate-200 rounded px-2 py-1.5 mt-0.5"
            />
          </div>
        </div>

        {error && (
          <p role="alert" className="text-xs text-rose-600 mt-3 bg-rose-50 border border-rose-200 rounded px-3 py-2">{error}</p>
        )}

        <button
          onClick={handleSave}
          disabled={saving}
          className="mt-4 w-full bg-slate-900 disabled:bg-slate-300 text-white text-sm font-semibold py-2.5 rounded-lg hover:bg-slate-800"
        >
          {saving ? "Adding…" : "Add line"}
        </button>
      </div>
    </div>
  );
}

function MatchModal({ line, onClose, onMatched }) {
  const [suggestions, setSuggestions] = useState(null);
  const [error, setError] = useState(null);
  const [matching, setMatching] = useState(null);
  const { authFetch } = useAuth();

  useEffect(() => {
    (async () => {
      try {
        const res = await authFetch(`${API_BASE}/reconciliation/suggestions/${line.id}`);
        if (!res.ok) throw new Error("Couldn't load suggestions");
        const data = await res.json();
        setSuggestions(data.suggestions || []);
      } catch (err) {
        setError(err.message);
      }
    })();
  }, [line.id, authFetch]);

  async function handleMatch(chargeId) {
    setMatching(chargeId);
    try {
      const res = await authFetch(`${API_BASE}/reconciliation/lines/${line.id}/match`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ chargeId }),
      });
      if (!res.ok) throw new Error("Couldn't save the match");
      onMatched();
      onClose();
    } catch (err) {
      setError(err.message);
      setMatching(null);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-30 p-4">
      <div className="bg-white rounded-xl shadow-lg w-full max-w-md p-5">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h3 className="font-semibold">Match: {line.description}</h3>
            <p className="text-xs text-slate-500">${line.amount.toLocaleString()} on {new Date(line.date).toLocaleDateString()}</p>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600">
            <X size={18} />
          </button>
        </div>

        {error && <p role="alert" className="text-xs text-rose-600 mb-3">{error}</p>}

        {!suggestions ? (
          <div className="h-24 bg-slate-100 rounded-xl animate-pulse" />
        ) : suggestions.length === 0 ? (
          <p className="text-sm text-slate-500">No charges found with a matching amount on this property.</p>
        ) : (
          <div className="space-y-2">
            {suggestions.map((s) => (
              <button
                key={s.chargeId}
                onClick={() => handleMatch(s.chargeId)}
                disabled={matching === s.chargeId}
                className="w-full text-left border border-slate-200 rounded-lg px-3 py-2 hover:border-indigo-300 hover:bg-indigo-50 disabled:opacity-50"
              >
                <div className="flex items-center justify-between text-sm">
                  <span>{s.description || "Charge"}</span>
                  <span className="font-mono">${s.amountDue.toLocaleString()}</span>
                </div>
                <p className="text-xs text-slate-500">Due {s.dueDate ? new Date(s.dueDate).toLocaleDateString() : "—"}</p>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function LineRow({ line, buildingName, onOpenMatch, onUnmatch }) {
  const isMatched = !!line.matchedChargeId;
  return (
    <div className="border-b border-slate-100 py-3 last:border-none">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium">{line.description}</span>
        <span className="text-sm font-mono">${line.amount.toLocaleString()}</span>
      </div>
      <div className="flex items-center justify-between mt-1">
        <p className="text-xs text-slate-500">
          {buildingName && <span>{buildingName} · </span>}
          {new Date(line.date).toLocaleDateString()}
        </p>
        {isMatched ? (
          <button onClick={() => onUnmatch(line.id)} className="flex items-center gap-1 text-[11px] text-emerald-700 hover:text-rose-600">
            <Link2 size={12} />
            Matched — unmatch
          </button>
        ) : (
          <button onClick={() => onOpenMatch(line)} className="flex items-center gap-1 text-[11px] text-indigo-700 hover:underline">
            <Link2Off size={12} />
            Find a match
          </button>
        )}
      </div>
    </div>
  );
}

export default function Reconciliation({ propertyId }) {
  const [lines, setLines] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showNew, setShowNew] = useState(false);
  const [matchingLine, setMatchingLine] = useState(null);
  const [showUnmatchedOnly, setShowUnmatchedOnly] = useState(true);
  const { authFetch, getPropertyName } = useAuth();

  const fetchLines = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (propertyId) params.set("propertyId", propertyId);
      if (showUnmatchedOnly) params.set("matched", "false");
      const res = await authFetch(`${API_BASE}/reconciliation/lines?${params.toString()}`);
      if (res.ok) {
        const data = await res.json();
        setLines(data.lines || []);
      } else {
        setError(res.status === 403 ? "You don't have access to this." : "Couldn't load statement lines — try again.");
      }
    } catch {
      setError("Couldn't load statement lines — check your connection and try again.");
    } finally {
      setLoading(false);
    }
  }, [propertyId, showUnmatchedOnly, authFetch]);

  useEffect(() => {
    fetchLines();
  }, [fetchLines]);

  async function handleUnmatch(lineId) {
    try {
      await authFetch(`${API_BASE}/reconciliation/lines/${lineId}/unmatch`, { method: "POST" });
      fetchLines();
    } catch {
      // fetchLines below will just show the current real state either way
      fetchLines();
    }
  }

  return (
    <div className="max-w-2xl mx-auto">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-lg font-semibold">Bank Reconciliation</h2>
        <button
          onClick={() => setShowNew(true)}
          disabled={!propertyId}
          title={!propertyId ? "Pick a specific building first" : undefined}
          className="flex items-center gap-1.5 text-sm font-semibold bg-slate-900 text-white px-3 py-1.5 rounded-lg hover:bg-slate-800 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          <Plus size={14} />
          Add line
        </button>
      </div>

      <label className="flex items-center gap-1.5 text-xs text-slate-500 mb-3">
        <input type="checkbox" checked={showUnmatchedOnly} onChange={(e) => setShowUnmatchedOnly(e.target.checked)} />
        Show unmatched lines only
      </label>

      {!propertyId && (
        <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 mb-3">
          Adding a line requires a specific building — pick one from the selector in the header first.
        </p>
      )}

      {loading ? (
        <div className="h-40 bg-slate-100 rounded-xl animate-pulse" />
      ) : error ? (
        <p role="alert" aria-live="polite" className="text-sm text-rose-600 bg-rose-50 border border-rose-200 rounded-xl px-4 py-3">{error}</p>
      ) : lines.length === 0 ? (
        <EmptyState
          icon={Landmark}
          title={showUnmatchedOnly ? "Nothing unmatched" : "No statement lines yet"}
          subtitle={showUnmatchedOnly ? "Everything entered so far has been matched to a charge." : "Add bank statement lines here to reconcile them against real charges."}
        />
      ) : (
        <div className="bg-white border border-slate-200 rounded-xl px-4">
          {lines.map((l) => (
            <LineRow
              key={l.id}
              line={l}
              buildingName={!propertyId ? getPropertyName(l.propertyId) : null}
              onOpenMatch={setMatchingLine}
              onUnmatch={handleUnmatch}
            />
          ))}
        </div>
      )}

      {showNew && (
        <NewLineModal propertyId={propertyId} onClose={() => setShowNew(false)} onSaved={fetchLines} />
      )}
      {matchingLine && (
        <MatchModal line={matchingLine} onClose={() => setMatchingLine(null)} onMatched={fetchLines} />
      )}
    </div>
  );
}
