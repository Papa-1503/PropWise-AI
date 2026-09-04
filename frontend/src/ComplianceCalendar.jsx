import { useState, useEffect, useCallback } from "react";
import { useAuth } from "./AuthContext";
import { API_BASE } from "./config";
import EmptyState from "./EmptyState";
import { Scale, AlertTriangle } from "lucide-react";

/**
 * ComplianceCalendar
 *
 * Real deadlines computed by backend/compliance_calendar_service.py
 * from staff-entered per-property rules (see PropertyManagement.jsx's
 * "Compliance" button) against real lease and move-out data. Never
 * shows a fabricated or generic deadline — a property with no rules
 * configured yet simply contributes nothing, shown honestly below
 * rather than silently.
 */

const TYPE_LABEL = {
  non_renewal_notice: "Non-renewal notice",
  deposit_return: "Deposit return",
};

function urgencyStyle(daysUntil) {
  if (daysUntil < 0) return "bg-rose-50 border-rose-200 text-rose-700";
  if (daysUntil <= 14) return "bg-amber-50 border-amber-200 text-amber-700";
  return "bg-slate-50 border-slate-200 text-slate-600";
}

function urgencyLabel(daysUntil) {
  if (daysUntil < 0) return `${Math.abs(daysUntil)}d overdue`;
  if (daysUntil === 0) return "Due today";
  return `${daysUntil}d left`;
}

export default function ComplianceCalendar({ propertyId }) {
  const [deadlines, setDeadlines] = useState(null);
  const [error, setError] = useState(null);
  const { authFetch } = useAuth();

  const fetchDeadlines = useCallback(async () => {
    setError(null);
    try {
      const params = new URLSearchParams();
      if (propertyId) params.set("propertyId", propertyId);
      const res = await authFetch(`${API_BASE}/compliance/calendar?${params.toString()}`);
      if (!res.ok) throw new Error("Couldn't load the compliance calendar.");
      const data = await res.json();
      setDeadlines(data.deadlines || []);
    } catch (err) {
      setError(err.message);
    }
  }, [propertyId, authFetch]);

  useEffect(() => {
    fetchDeadlines();
  }, [fetchDeadlines]);

  return (
    <div className="max-w-2xl mx-auto p-5 bg-white rounded-xl border border-slate-200">
      <div className="flex items-center gap-2 mb-1">
        <Scale size={18} className="text-slate-500" />
        <h2 className="text-lg font-semibold">Compliance Calendar</h2>
      </div>
      <p className="text-xs text-slate-500 mb-4">
        Real deadlines computed from what you've entered under each building's "Compliance" settings — not
        legal advice, and not a substitute for verifying your own state's current requirements.
      </p>

      {error && (
        <p role="alert" className="text-sm text-rose-600 bg-rose-50 border border-rose-200 rounded-xl px-4 py-3">
          {error}
        </p>
      )}

      {!error && deadlines === null && (
        <div className="h-32 bg-slate-100 rounded-xl animate-pulse" />
      )}

      {!error && deadlines !== null && deadlines.length === 0 && (
        <EmptyState
          icon={Scale}
          title="No upcoming deadlines"
          subtitle="Either nothing is due soon, or no building has compliance rules configured yet — set them under Properties → Compliance."
        />
      )}

      {!error && deadlines && deadlines.length > 0 && (
        <div className="space-y-2">
          {deadlines.map((d, i) => (
            <div key={i} className={`border rounded-lg px-3 py-2.5 ${urgencyStyle(d.daysUntilDeadline)}`}>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  {d.daysUntilDeadline <= 14 && <AlertTriangle size={13} />}
                  <span className="text-xs font-mono uppercase tracking-wide">{TYPE_LABEL[d.type] || d.type}</span>
                </div>
                <span className="text-[11px] font-semibold">{urgencyLabel(d.daysUntilDeadline)}</span>
              </div>
              <p className="text-sm text-slate-700 mt-1">
                {d.propertyName && <span className="font-medium">{d.propertyName} · </span>}
                {d.description}
              </p>
              <p className="text-[11px] text-slate-400 mt-0.5">
                Deadline: {new Date(d.deadline).toLocaleDateString()}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
