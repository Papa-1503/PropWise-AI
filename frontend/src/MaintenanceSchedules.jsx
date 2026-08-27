import { useState, useEffect, useCallback, useId } from "react";
import { useAuth } from "./AuthContext";
import EmptyState from "./EmptyState";
import { CalendarClock, Plus, X } from "lucide-react";
import { API_BASE } from "./config";

/**
 * MaintenanceSchedules
 *
 * Priority 46 — the actual automation already works end-to-end
 * (Priority 5: the admin trigger correctly finds due schedules, creates
 * tickets, and advances next-due-dates). What was missing was purely
 * the ability to create and view schedules through the UI, rather than
 * direct API calls.
 */

const CATEGORY_OPTIONS = ["general", "plumbing", "electrical", "hvac", "landscaping", "locksmith"];

function NewScheduleModal({ propertyId, onClose, onSaved }) {
  const [unitId, setUnitId] = useState("");
  const [title, setTitle] = useState("");
  const [category, setCategory] = useState("general");
  const [intervalDays, setIntervalDays] = useState("90");
  const [nextDueDate, setNextDueDate] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const { authFetch } = useAuth();
  const idPrefix = useId();

  async function handleSave() {
    if (!title.trim() || !nextDueDate) {
      setError("Title and a next due date are required.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const res = await authFetch(`${API_BASE}/maintenance-schedules`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          propertyId,
          unitId: unitId || null,
          title,
          category,
          intervalDays: Number(intervalDays),
          nextDueDate,
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
          <h3 className="font-semibold">New maintenance schedule</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600">
            <X size={18} />
          </button>
        </div>

        <div className="space-y-3">
          <div>
            <label htmlFor={`${idPrefix}-title`} className="text-xs text-slate-500">Title</label>
            <input
              id={`${idPrefix}-title`}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. HVAC filter check"
              className="w-full text-sm border border-slate-200 rounded px-2 py-1.5 mt-0.5"
            />
          </div>
          <div>
            <label htmlFor={`${idPrefix}-unit`} className="text-xs text-slate-500">Unit (optional — leave blank for property-wide, e.g. shared HVAC, common areas)</label>
            <input
              id={`${idPrefix}-unit`}
              value={unitId}
              onChange={(e) => setUnitId(e.target.value)}
              placeholder="e.g. 104"
              className="w-full text-sm border border-slate-200 rounded px-2 py-1.5 mt-0.5"
            />
          </div>
          <div className="flex gap-3">
            <div className="flex-1">
              <label htmlFor={`${idPrefix}-category`} className="text-xs text-slate-500">Category</label>
              <select
                id={`${idPrefix}-category`}
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                className="w-full text-sm border border-slate-200 rounded px-2 py-1.5 mt-0.5 capitalize"
              >
                {CATEGORY_OPTIONS.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </div>
            <div className="flex-1">
              <label htmlFor={`${idPrefix}-interval`} className="text-xs text-slate-500">Repeats every (days)</label>
              <input
                id={`${idPrefix}-interval`}
                type="number"
                value={intervalDays}
                onChange={(e) => setIntervalDays(e.target.value)}
                className="w-full text-sm border border-slate-200 rounded px-2 py-1.5 mt-0.5"
              />
            </div>
          </div>
          <div>
            <label htmlFor={`${idPrefix}-due`} className="text-xs text-slate-500">Next due date</label>
            <input
              id={`${idPrefix}-due`}
              type="date"
              value={nextDueDate}
              onChange={(e) => setNextDueDate(e.target.value)}
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
          {saving ? "Creating…" : "Create schedule"}
        </button>
      </div>
    </div>
  );
}

function ScheduleRow({ schedule, buildingName }) {
  return (
    <div className="border-b border-slate-100 py-3 last:border-none">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium">{schedule.title}</span>
        <span className="text-[11px] font-mono uppercase px-2 py-0.5 rounded-full border bg-slate-50 text-slate-500 border-slate-200 capitalize">
          {schedule.category}
        </span>
      </div>
      <p className="text-xs text-slate-500 mt-1">
        {buildingName && <span>{buildingName} · </span>}
        {schedule.unitId ? `Unit ${schedule.unitId}` : "Property-wide"} · every {schedule.intervalDays} days · next due{" "}
        {new Date(schedule.nextDueDate).toLocaleDateString()}
      </p>
    </div>
  );
}

export default function MaintenanceSchedules({ propertyId }) {
  const [schedules, setSchedules] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showNew, setShowNew] = useState(false);
  const { authFetch, getPropertyName } = useAuth();

  const fetchSchedules = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (propertyId) params.set("propertyId", propertyId);
      const res = await authFetch(`${API_BASE}/maintenance-schedules?${params.toString()}`);
      if (res.ok) {
        const data = await res.json();
        setSchedules(data.schedules || []);
      } else {
        setError(res.status === 403 ? "You don't have access to this." : "Couldn't load schedules — try again.");
      }
    } catch {
      setError("Couldn't load schedules — check your connection and try again.");
    } finally {
      setLoading(false);
    }
  }, [propertyId, authFetch]);

  useEffect(() => {
    fetchSchedules();
  }, [fetchSchedules]);

  return (
    <div className="max-w-2xl mx-auto">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-lg font-semibold">Preventive Maintenance</h2>
        <button
          onClick={() => setShowNew(true)}
          disabled={!propertyId}
          title={!propertyId ? "Pick a specific building first" : undefined}
          className="flex items-center gap-1.5 text-sm font-semibold bg-slate-900 text-white px-3 py-1.5 rounded-lg hover:bg-slate-800 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          <Plus size={14} />
          New schedule
        </button>
      </div>

      {!propertyId && (
        <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 mb-3">
          Creating a schedule requires a specific building — pick one from the selector in the header first.
        </p>
      )}

      {loading ? (
        <div className="h-40 bg-slate-100 rounded-xl animate-pulse" />
      ) : error ? (
        <p role="alert" aria-live="polite" className="text-sm text-rose-600 bg-rose-50 border border-rose-200 rounded-xl px-4 py-3">{error}</p>
      ) : schedules.length === 0 ? (
        <EmptyState
          icon={CalendarClock}
          title="No maintenance schedules yet"
          subtitle="Recurring tasks like filter changes or inspections show up here once created."
        />
      ) : (
        <div className="bg-white border border-slate-200 rounded-xl px-4">
          {schedules.map((s) => (
            <ScheduleRow key={s.id} schedule={s} buildingName={!propertyId ? getPropertyName(s.propertyId) : null} />
          ))}
        </div>
      )}

      {showNew && (
        <NewScheduleModal propertyId={propertyId} onClose={() => setShowNew(false)} onSaved={fetchSchedules} />
      )}
    </div>
  );
}
