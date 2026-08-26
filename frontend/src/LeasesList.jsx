import { useState, useEffect, useCallback } from "react";
import { useAuth } from "./AuthContext";
import EmptyState from "./EmptyState";
import { FileSignature, Plus, X, FileText } from "lucide-react";
import { API_BASE } from "./config";

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
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [rent, setRent] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const { authFetch } = useAuth();

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
          startDate,
          endDate,
          rent: rent ? Number(rent) : 0,
        }),
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
          <h3 className="font-semibold">New lease</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600">
            <X size={18} />
          </button>
        </div>

        <div className="space-y-3">
          <div>
            <label className="text-xs text-slate-500">Unit</label>
            <input
              value={unitId}
              onChange={(e) => setUnitId(e.target.value)}
              placeholder="e.g. 104"
              className="w-full text-sm border border-slate-200 rounded px-2 py-1.5 mt-0.5"
            />
          </div>
          <div>
            <label className="text-xs text-slate-500">Resident name</label>
            <input
              value={residentName}
              onChange={(e) => setResidentName(e.target.value)}
              className="w-full text-sm border border-slate-200 rounded px-2 py-1.5 mt-0.5"
            />
          </div>
          <div>
            <label className="text-xs text-slate-500">Resident email (optional)</label>
            <input
              value={residentEmail}
              onChange={(e) => setResidentEmail(e.target.value)}
              placeholder="Needed to generate a lease document"
              className="w-full text-sm border border-slate-200 rounded px-2 py-1.5 mt-0.5"
            />
          </div>
          <div className="flex gap-3">
            <div className="flex-1">
              <label className="text-xs text-slate-500">Start date</label>
              <input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="w-full text-sm border border-slate-200 rounded px-2 py-1.5 mt-0.5"
              />
            </div>
            <div className="flex-1">
              <label className="text-xs text-slate-500">End date</label>
              <input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className="w-full text-sm border border-slate-200 rounded px-2 py-1.5 mt-0.5"
              />
            </div>
          </div>
          <div>
            <label className="text-xs text-slate-500">Monthly rent</label>
            <input
              type="number"
              value={rent}
              onChange={(e) => setRent(e.target.value)}
              className="w-full text-sm border border-slate-200 rounded px-2 py-1.5 mt-0.5"
            />
          </div>
        </div>

        {error && (
          <p className="text-xs text-rose-600 mt-3 bg-rose-50 border border-rose-200 rounded px-3 py-2">{error}</p>
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

function LeaseRow({ lease, buildingName, onRenewalChange, onGenerateDocument }) {
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
        <div>
          <span className="text-sm font-medium">{lease.residentName}</span>
          <span className="text-xs text-slate-500 ml-2">
            {buildingName && <span>{buildingName} · </span>}
            Unit {lease.unitId}
          </span>
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
  const [error, setError] = useState(null);
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

  return (
    <div className="max-w-2xl mx-auto">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-lg font-semibold">Leases</h2>
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

      {!propertyId && (
        <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 mb-3">
          Creating a lease requires a specific building — pick one from the selector in the header first.
        </p>
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
      ) : (
        <div className="bg-white border border-slate-200 rounded-xl px-4">
          {leases.map((l) => (
            <LeaseRow
              key={l.id}
              lease={l}
              buildingName={!propertyId ? getPropertyName(l.propertyId) : null}
              onRenewalChange={handleRenewalChange}
              onGenerateDocument={handleGenerateDocument}
            />
          ))}
        </div>
      )}

      {showNew && (
        <NewLeaseModal propertyId={propertyId} onClose={() => setShowNew(false)} onSaved={fetchLeases} />
      )}
    </div>
  );
}
