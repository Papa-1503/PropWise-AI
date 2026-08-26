import { useState, useEffect, useCallback } from "react";
import { useAuth } from "./AuthContext";
import EmptyState from "./EmptyState";
import { Users } from "lucide-react";
import { API_BASE } from "./config";

/**
 * StaffAssignments
 *
 * Priority 45 — no way previously existed to view or change which
 * techs are assigned to which properties; this only ever got set via
 * direct API calls or the scale-test seed script. Real backend
 * (routers/staff.py) already worked — same gap pattern as several
 * others found today.
 */

function StaffRow({ staffMember, properties, onToggle }) {
  const assigned = new Set(staffMember.assignedProperties || []);

  return (
    <div className="border-b border-slate-100 py-3 last:border-none">
      <p className="text-sm font-medium mb-2">{staffMember.name}</p>
      <div className="flex flex-wrap gap-1.5">
        {properties.map((p) => {
          const isAssigned = assigned.has(p.id);
          return (
            <button
              key={p.id}
              onClick={() => onToggle(staffMember.id, p.id, !isAssigned)}
              className={`text-[11px] px-2 py-1 rounded-full border ${
                isAssigned
                  ? "bg-indigo-50 text-indigo-700 border-indigo-200"
                  : "bg-white text-slate-400 border-slate-200 hover:border-slate-300"
              }`}
            >
              {p.name}
            </button>
          );
        })}
      </div>
    </div>
  );
}

export default function StaffAssignments() {
  const [staff, setStaff] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const { authFetch, properties } = useAuth();

  const fetchStaff = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await authFetch(`${API_BASE}/staff`);
      if (res.ok) {
        const data = await res.json();
        setStaff(data.staff || []);
      } else {
        setError(res.status === 403 ? "You don't have access to this." : "Couldn't load staff — try again.");
      }
    } catch {
      setError("Couldn't load staff — check your connection and try again.");
    } finally {
      setLoading(false);
    }
  }, [authFetch]);

  useEffect(() => {
    fetchStaff();
  }, [fetchStaff]);

  async function handleToggle(staffId, propertyId, shouldAssign) {
    // Optimistic update, matching the pattern used across the panels
    // built earlier today (Leases, Screening, Leads).
    setStaff((prev) =>
      prev.map((s) => {
        if (s.id !== staffId) return s;
        const current = new Set(s.assignedProperties || []);
        if (shouldAssign) current.add(propertyId);
        else current.delete(propertyId);
        return { ...s, assignedProperties: [...current] };
      })
    );

    const target = staff.find((s) => s.id === staffId);
    const current = new Set(target?.assignedProperties || []);
    if (shouldAssign) current.add(propertyId);
    else current.delete(propertyId);

    try {
      await authFetch(`${API_BASE}/staff/${staffId}/properties`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ assignedProperties: [...current] }),
      });
    } catch {
      fetchStaff(); // revert to real state if the save failed
    }
  }

  return (
    <div className="max-w-2xl mx-auto">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-lg font-semibold">Staff Assignments</h2>
      </div>

      <p className="text-xs text-slate-500 bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 mb-3">
        Click a building to assign or unassign it — determines who gets notified for maintenance requests at that property.
      </p>

      {loading ? (
        <div className="h-40 bg-slate-100 rounded-xl animate-pulse" />
      ) : error ? (
        <p role="alert" aria-live="polite" className="text-sm text-rose-600 bg-rose-50 border border-rose-200 rounded-xl px-4 py-3">{error}</p>
      ) : staff.length === 0 ? (
        <EmptyState icon={Users} title="No staff accounts yet" subtitle="Staff accounts show up here once created." />
      ) : (
        <div className="bg-white border border-slate-200 rounded-xl px-4">
          {staff.map((s) => (
            <StaffRow key={s.id} staffMember={s} properties={properties} onToggle={handleToggle} />
          ))}
        </div>
      )}
    </div>
  );
}
