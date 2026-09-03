import { useState, useEffect, useCallback, useId, useMemo } from "react";
import { useAuth } from "./AuthContext";
import { useToast } from "./ToastContext";
import EmptyState from "./EmptyState";
import { FileSignature, Plus, X, FileText, Search, AlertTriangle } from "lucide-react";
import { API_BASE } from "./config";
import Resident360Modal from "./Resident360Modal";
import UnitHistoryModal from "./UnitHistoryModal";
import RenewalRiskPanel from "./RenewalRiskPanel";

/**
 * LeasesList
 *
 * The most critical frontend gap found in today's full-app sweep: the
 * leases backend (routers/leases.py) has always worked, but there was
 * no way to actually create or manage a lease through the app — only
 * via direct API calls. This is the core object of the whole business,
 * so this was the highest-priority fix among the six gaps found.
 */

const RENEWAL_STYLE = {
  not_sent: "bg-slate-50 text-slate-500 border-slate-200",
  sent: "bg-amber-50 text-amber-700 border-amber-200",
  signed: "bg-emerald-50 text-emerald-700 border-emerald-200",
};

function NewLeaseModal({ propertyId, onClose, onSaved }) {
  const [unitId, setUnitId] = useState("");
  const [residentName, setResidentName] = useState("");
  const [residentEmail, setResidentEmail] = useState("");
  const [residentPhone, setResidentPhone] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [rent, setRent] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const { authFetch } = useAuth();
  const { show: showToast } = useToast();
  const idPrefix = useId();

  async function handleSave() {
    if (!unitId.trim() || !residentName.trim() || !startDate || !endDate) {
      setError("Unit, resident name, and both dates are required.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const res = await authFetch(`${API_BASE}/leases`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          propertyId,
          unitId,
          residentName,
          residentEmail: residentEmail || null,
          residentPhone: residentPhone || null,
          startDate,
          endDate,
          rent: rent ? Number(rent) : 0,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Something went wrong");
      showToast(`Lease created for ${residentName} (Unit ${unitId})`, "success");
      onSaved();
      onClose();
    } catch (err) {
      showToast(err.message || "Couldn't create the lease.", "error");
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-30 p-4">
      <div className="bg-white rounded-xl shadow-lg w-full max-w-md p-5">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-semibold">New lease</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600">
            <X size={18} />
          </button>
        </div>

        <div className="space-y-3">
          <div>
            <label htmlFor={`${idPrefix}-unit`} className="text-xs text-slate-500">Unit</label>
            <input
              id={`${idPrefix}-unit`}
              value={unitId}
              onChange={(e) => setUnitId(e.target.value)}
              placeholder="e.g. 104"
              className="w-full text-sm border border-slate-200 rounded px-2 py-1.5 mt-0.5"
            />
          </div>
          <div>
            <label htmlFor={`${idPrefix}-name`} className="text-xs text-slate-500">Resident name</label>
            <input
              id={`${idPrefix}-name`}
              autoComplete="name"
              value={residentName}
              onChange={(e) => setResidentName(e.target.value)}
              className="w-full text-sm border border-slate-200 rounded px-2 py-1.5 mt-0.5"
            />
          </div>
          <div>
            <label htmlFor={`${idPrefix}-email`} className="text-xs text-slate-500">Resident email (optional)</label>
            <input
              id={`${idPrefix}-email`}
              type="email"
              autoComplete="email"
              value={residentEmail}
              onChange={(e) => setResidentEmail(e.target.value)}
              placeholder="Needed to generate a lease document"
              className="w-full text-sm border border-slate-200 rounded px-2 py-1.5 mt-0.5"
            />
          </div>
          <div>
            <label htmlFor={`${idPrefix}-phone`} className="text-xs text-slate-500">Resident phone (optional)</label>
            <input
              id={`${idPrefix}-phone`}
              type="tel"
              autoComplete="tel"
              value={residentPhone}
              onChange={(e) => setResidentPhone(e.target.value)}
              placeholder="612-555-0100"
              className="w-full text-sm border border-slate-200 rounded px-2 py-1.5 mt-0.5"
            />
          </div>
          <div className="flex gap-3">
            <div className="flex-1">
              <label htmlFor={`${idPrefix}-start`} className="text-xs text-slate-500">Start date</label>
              <input
                id={`${idPrefix}-start`}
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="w-full text-sm border border-slate-200 rounded px-2 py-1.5 mt-0.5"
              />
            </div>
            <div className="flex-1">
              <label htmlFor={`${idPrefix}-end`} className="text-xs text-slate-500">End date</label>
              <input
                id={`${idPrefix}-end`}
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className="w-full text-sm border border-slate-200 rounded px-2 py-1.5 mt-0.5"
              />
            </div>
          </div>
          <div>
            <label htmlFor={`${idPrefix}-rent`} className="text-xs text-slate-500">Monthly rent</label>
            <input
              id={`${idPrefix}-rent`}
              type="number"
              value={rent}
              onChange={(e) => setRent(e.target.value)}
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
          {saving ? "Creating…" : "Create lease"}
        </button>
      </div>
    </div>
  );
}

function LeaseRow({ lease, buildingName, onRenewalChange, onGenerateDocument, onViewHistory, selectable, selected, onToggleSelect }) {
  const [generating, setGenerating] = useState(false);
  const [copied, setCopied] = useState(false);

  async function handleGenerate() {
    setGenerating(true);
    try {
      await onGenerateDocument(lease.id);
    } finally {
      setGenerating(false);
    }
  }

  return (
    <div className="border-b border-slate-100 py-3 last:border-none">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {selectable && (
            <input
              type="checkbox"
              checked={selected}
              onChange={() => onToggleSelect(lease.id)}
              aria-label={`Select ${lease.residentName}`}
            />
          )}
          <div>
            <span className="text-sm font-medium">{lease.residentName}</span>
            <span className="text-xs text-slate-500 ml-2">
              {buildingName && <span>{buildingName} · </span>}
              <button
                onClick={() => onViewHistory(lease)}
                title={lease.residentEmail ? "View this resident's full history" : "View this unit's history"}
                className="underline decoration-dotted hover:text-indigo-600 hover:decoration-solid"
              >
                Unit {lease.unitId}
              </button>
            </span>
          </div>
        </div>
        <select
          value={lease.renewalStatus}
          onChange={(e) => onRenewalChange(lease.id, e.target.value)}
          className={`text-[11px] font-mono uppercase px-2 py-0.5 rounded-full border ${RENEWAL_STYLE[lease.renewalStatus]}`}
        >
          <option value="not_sent">Not Sent</option>
          <option value="sent">Sent</option>
          <option value="signed">Signed</option>
        </select>
      </div>
      <div className="flex items-center justify-between mt-1">
        <p className="text-xs text-slate-500">
          {new Date(lease.startDate).toLocaleDateString()} – {new Date(lease.endDate).toLocaleDateString()} ·{" "}
          ${lease.rent.toLocaleString()}/mo
        </p>
        <div className="flex items-center gap-3">
          {lease.inviteCode && (
            <button
              onClick={() => {
                navigator.clipboard?.writeText(lease.inviteCode);
                setCopied(true);
                setTimeout(() => setCopied(false), 1500);
              }}
              title="Copy invite code to share with the resident"
              className="text-[11px] font-mono text-slate-500 hover:text-slate-700 tracking-wider"
            >
              {copied ? "Copied!" : lease.inviteCode}
            </button>
          )}
          <button
            onClick={handleGenerate}
            disabled={generating || !lease.residentEmail}
            title={!lease.residentEmail ? "No resident email on file" : "Generate lease document"}
            className="flex items-center gap-1 text-[11px] text-indigo-700 hover:underline disabled:text-slate-300 disabled:cursor-not-allowed"
          >
            <FileText size={12} />
            {generating ? "Generating…" : "Generate document"}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function LeasesList({ propertyId }) {
  const [leases, setLeases] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showNew, setShowNew] = useState(false);
  const [showRisk, setShowRisk] = useState(false);
  const [error, setError] = useState(null);
  // { email, name } for a resident-scoped lookup, or { propertyId, unitId }
  // for a unit-scoped fallback when no resident email is on file — set by
  // handleViewHistory below, which decides the shape based on the lease.
  const [historyTarget, setHistoryTarget] = useState(null);
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [confirmingBulk, setConfirmingBulk] = useState(null); // target renewalStatus | null
  const [undoState, setUndoState] = useState(null);
  const [search, setSearch] = useState("");
  const { authFetch, getPropertyName } = useAuth();

  const fetchLeases = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (propertyId) params.set("propertyId", propertyId);
      const res = await authFetch(`${API_BASE}/leases?${params.toString()}`);
      if (res.ok) {
        const data = await res.json();
        setLeases(data.leases || []);
      } else {
        setError(res.status === 403 ? "You don't have access to this." : "Couldn't load leases — try again.");
      }
    } catch {
      setError("Couldn't load leases — check your connection and try again.");
    } finally {
      setLoading(false);
    }
  }, [propertyId, authFetch]);

  useEffect(() => {
    fetchLeases();
  }, [fetchLeases]);

  function handleViewHistory(lease) {
    // A resident email means we can look them up across every unit
    // they've ever lived in (Resident360Modal, /api/residents/360).
    // No email — vacant unit, or an occupied one created without an
    // email on file — falls back to a unit-scoped lookup instead
    // (UnitHistoryModal, /api/units/360), so the unit number is always
    // clickable and always opens something useful either way.
    if (lease.residentEmail) {
      setHistoryTarget({ email: lease.residentEmail, name: lease.residentName });
    } else {
      setHistoryTarget({ propertyId: lease.propertyId, unitId: lease.unitId });
    }
  }

  async function handleRenewalChange(leaseId, renewalStatus) {
    setLeases((prev) => prev.map((l) => (l.id === leaseId ? { ...l, renewalStatus } : l)));
    try {
      await authFetch(`${API_BASE}/leases/${leaseId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ renewalStatus }),
      });
    } catch {
      fetchLeases(); // revert to real state if the save failed
    }
  }

  const RENEWAL_LABEL = { not_sent: "Not Sent", sent: "Sent", signed: "Signed" };

  function toggleSelect(leaseId) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(leaseId)) next.delete(leaseId);
      else next.add(leaseId);
      return next;
    });
  }

  function applyBulkRenewalStatus(renewalStatus) {
    const affectedIds = [...selectedIds];
    const previousStatuses = new Map(
      leases.filter((l) => affectedIds.includes(l.id)).map((l) => [l.id, l.renewalStatus])
    );

    setLeases((prev) => prev.map((l) => (affectedIds.includes(l.id) ? { ...l, renewalStatus } : l)));
    setSelectedIds(new Set());
    setConfirmingBulk(null);

    // Set undo state before awaiting the network calls, not after — see
    // MaintenanceTickets.jsx's applyBulkStatus for why (real testing
    // there showed the state wasn't reliably persisting when set after
    // an await, even though it was genuinely being called with correct
    // data). This also gives instant feedback either way.
    setUndoState({
      previousStatuses,
      message: `${affectedIds.length} lease${affectedIds.length !== 1 ? "s" : ""} marked ${RENEWAL_LABEL[renewalStatus]}.`,
    });
    setTimeout(() => setUndoState((cur) => (cur?.previousStatuses === previousStatuses ? null : cur)), 8000);

    Promise.all(
      affectedIds.map((id) =>
        authFetch(`${API_BASE}/leases/${id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ renewalStatus }),
        }).catch(() => null)
      )
    );
  }

  async function handleUndo() {
    if (!undoState) return;
    const { previousStatuses } = undoState;
    setLeases((prev) =>
      prev.map((l) => (previousStatuses.has(l.id) ? { ...l, renewalStatus: previousStatuses.get(l.id) } : l))
    );
    setUndoState(null);
    await Promise.all(
      [...previousStatuses.entries()].map(([id, renewalStatus]) =>
        authFetch(`${API_BASE}/leases/${id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ renewalStatus }),
        }).catch(() => null)
      )
    );
  }

  async function handleGenerateDocument(leaseId) {
    const res = await authFetch(`${API_BASE}/leases/${leaseId}/generate-document`, { method: "POST" });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      alert(data.detail || "Couldn't generate the document.");
    } else if (data.alreadyExisted) {
      alert("A lease document was already generated and is still pending signature — check the Documents tab.");
    } else {
      alert("Lease document generated — check the Documents tab.");
    }
  }

  // Resident name matches partially (typing "Devon" should find "Devon
  // Walker"), unit number matches exactly — same lesson learned from
  // Properties search earlier: a substring match on unit numbers
  // produces confusing false positives ("105" also matching "1105"),
  // which is a real problem for numbers in a way it isn't for names.
  const filteredLeases = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return leases;
    return leases.filter(
      (l) => (l.residentName || "").toLowerCase().includes(q) || (l.unitId || "").toLowerCase() === q
    );
  }, [leases, search]);

  return (
    <div className="max-w-2xl mx-auto">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-lg font-semibold">Leases</h2>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowRisk((v) => !v)}
            className="flex items-center gap-1.5 text-sm font-semibold border border-slate-200 text-slate-700 px-3 py-1.5 rounded-lg hover:bg-slate-50"
          >
            <AlertTriangle size={14} className="text-amber-500" />
            {showRisk ? "Hide" : "View"} renewal risk
          </button>
          <button
            onClick={() => setShowNew(true)}
            disabled={!propertyId}
            title={!propertyId ? "Pick a specific building first" : undefined}
            className="flex items-center gap-1.5 text-sm font-semibold bg-slate-900 text-white px-3 py-1.5 rounded-lg hover:bg-slate-800 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <Plus size={14} />
            New lease
          </button>
        </div>
      </div>

      {showRisk && (
        <div className="mb-4">
          <RenewalRiskPanel propertyId={propertyId} />
        </div>
      )}

      {!propertyId && (
        <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 mb-3">
          Creating a lease requires a specific building — pick one from the selector in the header first.
        </p>
      )}

      {!loading && !error && leases.length > 0 && (
        <div className="relative mb-3">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by resident name or unit number…"
            className="w-full text-sm border border-slate-200 rounded-lg pl-9 pr-3 py-2"
          />
        </div>
      )}

      {selectedIds.size > 0 && (
        <div className="flex items-center justify-between bg-slate-900 text-white rounded-lg px-4 py-2.5 mb-3 text-sm">
          <span>{selectedIds.size} selected</span>
          <div className="flex gap-2">
            {["not_sent", "sent", "signed"].map((s) => (
              <button
                key={s}
                onClick={() => setConfirmingBulk(s)}
                className="text-xs font-semibold bg-white/10 hover:bg-white/20 px-2.5 py-1 rounded"
              >
                Mark {RENEWAL_LABEL[s]}
              </button>
            ))}
            <button onClick={() => setSelectedIds(new Set())} className="text-xs text-slate-300 hover:text-white px-2">
              Clear
            </button>
          </div>
        </div>
      )}

      {confirmingBulk && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-30 p-4">
          <div className="bg-white rounded-xl shadow-lg w-full max-w-sm p-5">
            <p className="text-sm mb-4">
              Mark <strong>{selectedIds.size}</strong> lease{selectedIds.size !== 1 ? "s" : ""} as{" "}
              <strong>{RENEWAL_LABEL[confirmingBulk]}</strong>?
            </p>
            <div className="flex gap-2">
              <button
                onClick={() => applyBulkRenewalStatus(confirmingBulk)}
                className="flex-1 text-sm font-semibold bg-slate-900 text-white py-2 rounded-lg"
              >
                Confirm
              </button>
              <button
                onClick={() => setConfirmingBulk(null)}
                className="flex-1 text-sm font-semibold bg-white border border-slate-300 py-2 rounded-lg"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {undoState && (
        <div className="fixed bottom-4 left-1/2 -translate-x-1/2 bg-slate-900 text-white text-sm px-4 py-2.5 rounded-lg shadow-lg flex items-center gap-3 z-30">
          <span>{undoState.message}</span>
          <button onClick={handleUndo} className="font-semibold underline">Undo</button>
        </div>
      )}

      {loading ? (
        <div className="h-40 bg-slate-100 rounded-xl animate-pulse" />
      ) : error ? (
        <p role="alert" aria-live="polite" className="text-sm text-rose-600 bg-rose-50 border border-rose-200 rounded-xl px-4 py-3">{error}</p>
      ) : leases.length === 0 ? (
        <EmptyState
          icon={FileSignature}
          title="No leases yet"
          subtitle="Create a lease for a new resident, or leases created elsewhere will show up here."
        />
      ) : filteredLeases.length === 0 ? (
        <p className="text-sm text-slate-400">No leases match "{search}".</p>
      ) : (
        <div className="bg-white border border-slate-200 rounded-xl px-4">
          {filteredLeases.map((l) => (
            <LeaseRow
              key={l.id}
              lease={l}
              buildingName={!propertyId ? getPropertyName(l.propertyId) : null}
              onRenewalChange={handleRenewalChange}
              onGenerateDocument={handleGenerateDocument}
              onViewHistory={handleViewHistory}
              selectable={true}
              selected={selectedIds.has(l.id)}
              onToggleSelect={toggleSelect}
            />
          ))}
        </div>
      )}

      {showNew && (
        <NewLeaseModal propertyId={propertyId} onClose={() => setShowNew(false)} onSaved={fetchLeases} />
      )}
      {historyTarget && historyTarget.email && (
        <Resident360Modal
          email={historyTarget.email}
          name={historyTarget.name}
          onClose={() => setHistoryTarget(null)}
        />
      )}
      {historyTarget && !historyTarget.email && (
        <UnitHistoryModal
          propertyId={historyTarget.propertyId}
          unitId={historyTarget.unitId}
          onClose={() => setHistoryTarget(null)}
        />
      )}
    </div>
  );
}
