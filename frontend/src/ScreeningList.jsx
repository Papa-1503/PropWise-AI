import { useState, useEffect, useCallback } from "react";
import { useAuth } from "./AuthContext";
import EmptyState from "./EmptyState";
import { UserSearch, Plus, X } from "lucide-react";
import { API_BASE } from "./config";

/**
 * ScreeningList
 *
 * Second of two tightly-coupled priorities built today (Leases, then
 * Screening) — the real-world workflow is applicant -> screening ->
 * lease, and both halves had zero frontend before today.
 *
 * Important: this is a request/status TRACKING tool, not a live credit
 * check. No real screening provider is wired in on the backend (see
 * routers/screening.py's docstring) — screening data involves FCRA-
 * protected consumer credit information, and this must not be used on
 * real applicants without the required business agreement and
 * compliance paperwork. The scoring shown is a transparent, staff-
 * entered weighted checklist, not a statistical credit model.
 */

const STATUS_STYLE = {
  pending: "bg-slate-50 text-slate-500 border-slate-200",
  in_progress: "bg-indigo-50 text-indigo-700 border-indigo-200",
  passed: "bg-emerald-50 text-emerald-700 border-emerald-200",
  failed: "bg-rose-50 text-rose-700 border-rose-200",
  manual_review: "bg-amber-50 text-amber-700 border-amber-200",
};
const STATUS_LABEL = {
  pending: "Pending",
  in_progress: "In Progress",
  passed: "Passed",
  failed: "Failed",
  manual_review: "Manual Review",
};

function NewRequestModal({ propertyId, onClose, onSaved }) {
  const [applicantName, setApplicantName] = useState("");
  const [applicantEmail, setApplicantEmail] = useState("");
  const [unitId, setUnitId] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const { authFetch } = useAuth();

  async function handleSave() {
    if (!applicantName.trim() || !applicantEmail.trim()) {
      setError("Applicant name and email are required.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const res = await authFetch(`${API_BASE}/screening`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          applicantName,
          applicantEmail,
          propertyId: propertyId || null,
          unitId: unitId || null,
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
          <h3 className="font-semibold">New screening request</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600">
            <X size={18} />
          </button>
        </div>

        <div className="space-y-3">
          <div>
            <label className="text-xs text-slate-500">Applicant name</label>
            <input
              value={applicantName}
              onChange={(e) => setApplicantName(e.target.value)}
              className="w-full text-sm border border-slate-200 rounded px-2 py-1.5 mt-0.5"
            />
          </div>
          <div>
            <label className="text-xs text-slate-500">Applicant email</label>
            <input
              value={applicantEmail}
              onChange={(e) => setApplicantEmail(e.target.value)}
              className="w-full text-sm border border-slate-200 rounded px-2 py-1.5 mt-0.5"
            />
          </div>
          <div>
            <label className="text-xs text-slate-500">Unit (optional)</label>
            <input
              value={unitId}
              onChange={(e) => setUnitId(e.target.value)}
              placeholder="e.g. 104"
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
          {saving ? "Creating…" : "Create request"}
        </button>
      </div>
    </div>
  );
}

function ScoreModal({ request, onClose, onSaved }) {
  const [creditScore, setCreditScore] = useState(request.creditScore ?? "");
  const [incomeToRentRatio, setIncomeToRentRatio] = useState(request.incomeToRentRatio ?? "");
  const [priorEvictions, setPriorEvictions] = useState(request.priorEvictions ?? "");
  const [rentalHistoryMonths, setRentalHistoryMonths] = useState(request.rentalHistoryMonths ?? "");
  const [notes, setNotes] = useState(request.notes ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const { authFetch } = useAuth();

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      const res = await authFetch(`${API_BASE}/screening/${request.id}/score`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          creditScore: creditScore === "" ? null : Number(creditScore),
          incomeToRentRatio: incomeToRentRatio === "" ? null : Number(incomeToRentRatio),
          priorEvictions: priorEvictions === "" ? null : Number(priorEvictions),
          rentalHistoryMonths: rentalHistoryMonths === "" ? null : Number(rentalHistoryMonths),
          notes: notes || null,
        }),
      });
      if (!res.ok) throw new Error("Couldn't save the score.");
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
          <h3 className="font-semibold">Score {request.applicantName}</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600">
            <X size={18} />
          </button>
        </div>

        <p className="text-xs text-slate-500 bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 mb-3">
          Manual entry only — no live credit/background check is connected. Screening data involves
          FCRA-protected information; don't use with real applicant data without proper compliance
          agreements in place.
        </p>

        <div className="space-y-3">
          <div>
            <label className="text-xs text-slate-500">Credit score</label>
            <input
              type="number"
              value={creditScore}
              onChange={(e) => setCreditScore(e.target.value)}
              className="w-full text-sm border border-slate-200 rounded px-2 py-1.5 mt-0.5"
            />
          </div>
          <div>
            <label className="text-xs text-slate-500">Income-to-rent ratio (e.g. 3.0 = 3x rent)</label>
            <input
              type="number"
              step="0.1"
              value={incomeToRentRatio}
              onChange={(e) => setIncomeToRentRatio(e.target.value)}
              className="w-full text-sm border border-slate-200 rounded px-2 py-1.5 mt-0.5"
            />
          </div>
          <div className="flex gap-3">
            <div className="flex-1">
              <label className="text-xs text-slate-500">Prior evictions</label>
              <input
                type="number"
                value={priorEvictions}
                onChange={(e) => setPriorEvictions(e.target.value)}
                className="w-full text-sm border border-slate-200 rounded px-2 py-1.5 mt-0.5"
              />
            </div>
            <div className="flex-1">
              <label className="text-xs text-slate-500">Rental history (months)</label>
              <input
                type="number"
                value={rentalHistoryMonths}
                onChange={(e) => setRentalHistoryMonths(e.target.value)}
                className="w-full text-sm border border-slate-200 rounded px-2 py-1.5 mt-0.5"
              />
            </div>
          </div>
          <div>
            <label className="text-xs text-slate-500">Notes (optional)</label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={2}
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
          {saving ? "Saving…" : "Save score"}
        </button>
      </div>
    </div>
  );
}

function ScreeningRow({ request, onStatusChange, onScoreClick }) {
  return (
    <div className="border-b border-slate-100 py-3 last:border-none">
      <div className="flex items-center justify-between">
        <div>
          <span className="text-sm font-medium">{request.applicantName}</span>
          <span className="text-xs text-slate-500 ml-2">{request.applicantEmail}</span>
        </div>
        <select
          value={request.status}
          onChange={(e) => onStatusChange(request.id, e.target.value)}
          className={`text-[11px] font-mono uppercase px-2 py-0.5 rounded-full border ${STATUS_STYLE[request.status]}`}
        >
          {Object.entries(STATUS_LABEL).map(([val, label]) => (
            <option key={val} value={val}>{label}</option>
          ))}
        </select>
      </div>
      <div className="flex items-center justify-between mt-1">
        <p className="text-xs text-slate-500">
          {request.unitId && <span>Unit {request.unitId} · </span>}
          {request.createdAt ? new Date(request.createdAt).toLocaleDateString() : ""}
          {typeof request.score === "number" && (
            <span className="ml-2 font-mono font-semibold text-slate-700">Score: {request.score}/100</span>
          )}
        </p>
        <button onClick={() => onScoreClick(request)} className="text-[11px] text-indigo-700 hover:underline">
          {typeof request.score === "number" ? "Update score" : "Enter score"}
        </button>
      </div>
    </div>
  );
}

export default function ScreeningList({ propertyId }) {
  const [requests, setRequests] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showNew, setShowNew] = useState(false);
  const [scoringRequest, setScoringRequest] = useState(null);
  const [error, setError] = useState(null);
  const { authFetch } = useAuth();

  const fetchRequests = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await authFetch(`${API_BASE}/screening`);
      if (res.ok) {
        const data = await res.json();
        let list = data.screeningRequests || [];
        if (propertyId) list = list.filter((r) => r.propertyId === propertyId);
        setRequests(list);
      } else {
        setError(res.status === 403 ? "You don't have access to this." : "Couldn't load screening requests — try again.");
      }
    } catch {
      setError("Couldn't load screening requests — check your connection and try again.");
    } finally {
      setLoading(false);
    }
  }, [propertyId, authFetch]);

  useEffect(() => {
    fetchRequests();
  }, [fetchRequests]);

  async function handleStatusChange(id, status) {
    setRequests((prev) => prev.map((r) => (r.id === id ? { ...r, status } : r)));
    try {
      await authFetch(`${API_BASE}/screening/${id}/status`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status }),
      });
    } catch {
      fetchRequests();
    }
  }

  return (
    <div className="max-w-2xl mx-auto">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-lg font-semibold">Tenant Screening</h2>
        <button
          onClick={() => setShowNew(true)}
          className="flex items-center gap-1.5 text-sm font-semibold bg-slate-900 text-white px-3 py-1.5 rounded-lg hover:bg-slate-800"
        >
          <Plus size={14} />
          New request
        </button>
      </div>

      <p className="text-xs text-slate-500 bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 mb-3">
        Request/status tracking only — no live credit or background check provider is connected.
      </p>

      {loading ? (
        <div className="h-40 bg-slate-100 rounded-xl animate-pulse" />
      ) : error ? (
        <p className="text-sm text-rose-600 bg-rose-50 border border-rose-200 rounded-xl px-4 py-3">{error}</p>
      ) : requests.length === 0 ? (
        <EmptyState
          icon={UserSearch}
          title="No screening requests yet"
          subtitle="Track applicants here as they move from pending through a decision."
        />
      ) : (
        <div className="bg-white border border-slate-200 rounded-xl px-4">
          {requests.map((r) => (
            <ScreeningRow
              key={r.id}
              request={r}
              onStatusChange={handleStatusChange}
              onScoreClick={setScoringRequest}
            />
          ))}
        </div>
      )}

      {showNew && (
        <NewRequestModal propertyId={propertyId} onClose={() => setShowNew(false)} onSaved={fetchRequests} />
      )}
      {scoringRequest && (
        <ScoreModal request={scoringRequest} onClose={() => setScoringRequest(null)} onSaved={fetchRequests} />
      )}
    </div>
  );
}
