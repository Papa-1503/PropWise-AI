import { useState, useEffect, useCallback, useId } from "react";
import { useAuth } from "./AuthContext";
import EmptyState from "./EmptyState";
import { PhoneCall, Plus, X } from "lucide-react";
import { API_BASE } from "./config";

/**
 * OnCall
 *
 * Real rebuild, not a resume of prior work — an earlier session
 * described building on-call rotation + Twilio Voice routing, but that
 * code has zero trace anywhere in this repo's git history on any
 * branch, so it never actually shipped. This is a genuine first pass:
 * shift CRUD plus the "who's on call right now" lookup, which is the
 * actual reason this feature exists. After-hours call routing itself
 * (the Twilio Voice piece) is real follow-on work, not included here.
 */

function formatShiftTime(iso) {
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function CurrentOnCallBanner({ propertyId }) {
  const [onCall, setOnCall] = useState(undefined); // undefined = loading, null = nobody
  const { authFetch } = useAuth();

  const fetchCurrent = useCallback(async () => {
    if (!propertyId) return;
    try {
      const res = await authFetch(`${API_BASE}/on-call/current?propertyId=${encodeURIComponent(propertyId)}`);
      const data = await res.json();
      setOnCall(data.onCall);
    } catch {
      setOnCall(null);
    }
  }, [propertyId, authFetch]);

  useEffect(() => {
    fetchCurrent();
  }, [fetchCurrent]);

  if (onCall === undefined) return null;

  return (
    <div
      className={`rounded-xl p-4 mb-4 flex items-center gap-3 ${
        onCall ? "bg-emerald-50 border border-emerald-100" : "bg-amber-50 border border-amber-100"
      }`}
    >
      <PhoneCall size={18} className={onCall ? "text-emerald-600" : "text-amber-600"} />
      {onCall ? (
        <div>
          <p className="text-sm font-medium text-emerald-800">
            {onCall.userName || "Someone"} is on call right now
          </p>
          <p className="text-xs text-emerald-600">
            Until {formatShiftTime(onCall.endTime)}
            {onCall.note && ` — ${onCall.note}`}
          </p>
        </div>
      ) : (
        <p className="text-sm font-medium text-amber-800">
          Nobody is currently scheduled for on-call at this property.
        </p>
      )}
    </div>
  );
}

function NewShiftModal({ propertyId, staff, onClose, onSaved }) {
  const [userId, setUserId] = useState(staff[0]?.id || "");
  const [startTime, setStartTime] = useState("");
  const [endTime, setEndTime] = useState("");
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const { authFetch } = useAuth();
  const idPrefix = useId();

  async function handleSave() {
    if (!userId || !startTime || !endTime) {
      setError("Staff member, start time, and end time are all required.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const res = await authFetch(`${API_BASE}/on-call/shifts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          userId,
          propertyIds: [propertyId],
          startTime,
          endTime,
          note: note || null,
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
      <div className="bg-white rounded-xl shadow-lg w-full max-w-sm p-5">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-semibold">New on-call shift</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600">
            <X size={18} />
          </button>
        </div>

        {error && <p role="alert" className="text-sm text-rose-600 mb-2">{error}</p>}

        <label htmlFor={`${idPrefix}-staff`} className="text-xs text-slate-500">Staff member</label>
        <select
          id={`${idPrefix}-staff`}
          value={userId}
          onChange={(e) => setUserId(e.target.value)}
          className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm mb-2 mt-0.5"
        >
          {staff.length === 0 && <option value="">No staff available</option>}
          {staff.map((s) => (
            <option key={s.id} value={s.id}>{s.name}</option>
          ))}
        </select>

        <label htmlFor={`${idPrefix}-start`} className="text-xs text-slate-500">Start</label>
        <input
          id={`${idPrefix}-start`}
          type="datetime-local"
          value={startTime}
          onChange={(e) => setStartTime(e.target.value)}
          className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm mb-2 mt-0.5"
        />

        <label htmlFor={`${idPrefix}-end`} className="text-xs text-slate-500">End</label>
        <input
          id={`${idPrefix}-end`}
          type="datetime-local"
          value={endTime}
          onChange={(e) => setEndTime(e.target.value)}
          className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm mb-2 mt-0.5"
        />

        <label htmlFor={`${idPrefix}-note`} className="text-xs text-slate-500">Note (optional)</label>
        <input
          id={`${idPrefix}-note`}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="e.g. covering for Alex"
          className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm mb-4 mt-0.5"
        />

        <button
          onClick={handleSave}
          disabled={saving}
          className="w-full bg-indigo-600 text-white text-sm font-medium py-2 rounded-lg disabled:opacity-50"
        >
          {saving ? "Saving…" : "Create shift"}
        </button>
      </div>
    </div>
  );
}

function ShiftRow({ shift, onDelete }) {
  const isPast = new Date(shift.endTime) < new Date();
  return (
    <div className={`flex items-center justify-between border-b border-slate-100 py-2.5 last:border-none ${isPast ? "opacity-50" : ""}`}>
      <div>
        <p className="text-sm font-medium">{shift.userName || "Unassigned"}</p>
        <p className="text-xs text-slate-500">
          {formatShiftTime(shift.startTime)} – {formatShiftTime(shift.endTime)}
          {shift.note && ` — ${shift.note}`}
        </p>
      </div>
      <button onClick={() => onDelete(shift.id)} className="text-slate-300 hover:text-rose-500 shrink-0">
        <X size={14} />
      </button>
    </div>
  );
}

export default function OnCall({ propertyId }) {
  const [shifts, setShifts] = useState([]);
  const [staff, setStaff] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showNew, setShowNew] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const { authFetch } = useAuth();

  const fetchShifts = useCallback(async () => {
    if (!propertyId) return;
    setLoading(true);
    try {
      const res = await authFetch(`${API_BASE}/on-call/shifts?propertyId=${encodeURIComponent(propertyId)}`);
      const data = await res.json();
      setShifts(data.shifts || []);
    } finally {
      setLoading(false);
    }
  }, [propertyId, authFetch]);

  useEffect(() => {
    fetchShifts();
  }, [fetchShifts, refreshKey]);

  useEffect(() => {
    (async () => {
      const res = await authFetch(`${API_BASE}/staff`);
      const data = await res.json();
      setStaff(data.staff || []);
    })();
  }, [authFetch]);

  async function handleDelete(shiftId) {
    await authFetch(`${API_BASE}/on-call/shifts/${shiftId}`, { method: "DELETE" });
    setRefreshKey((k) => k + 1);
  }

  if (!propertyId) {
    return <EmptyState icon={PhoneCall} title="Select a property" subtitle="On-call rotation is set per property." />;
  }

  return (
    <div className="max-w-2xl">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-lg font-semibold">On-call rotation</h2>
        <button
          onClick={() => setShowNew(true)}
          className="flex items-center gap-1 text-sm bg-indigo-600 text-white px-3 py-1.5 rounded-lg"
        >
          <Plus size={14} /> New shift
        </button>
      </div>

      <CurrentOnCallBanner propertyId={propertyId} />

      <div className="bg-white border border-slate-100 rounded-xl p-4">
        {loading ? (
          <div className="h-24 bg-slate-100 rounded-xl animate-pulse" />
        ) : shifts.length === 0 ? (
          <EmptyState icon={PhoneCall} title="No shifts scheduled" subtitle="Add a shift to start the rotation for this property." />
        ) : (
          shifts.map((s) => <ShiftRow key={s.id} shift={s} onDelete={handleDelete} />)
        )}
      </div>

      {showNew && (
        <NewShiftModal
          propertyId={propertyId}
          staff={staff}
          onClose={() => setShowNew(false)}
          onSaved={() => setRefreshKey((k) => k + 1)}
        />
      )}
    </div>
  );
}
