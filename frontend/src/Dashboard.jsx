import { useState, useEffect, useCallback } from "react";
import { useAuth } from "./AuthContext";
import { API_BASE } from "./config";
import AffirmationBanner from "./AffirmationBanner";

/**
 * Dashboard
 *
 * Pulls real aggregate numbers from GET /api/dashboard/stats — nothing
 * hardcoded. Pair with MaintenanceTickets / InspectionChecklist / AICopilot
 * for the full flow.
 */

const TONE_STYLES = {
  up: { from: "#10b981", to: "#34d399", text: "text-emerald-600", icon: "↑" },
  down: { from: "#f43f5e", to: "#fb7185", text: "text-rose-600", icon: "↓" },
  neutral: { from: "#0ea5e9", to: "#38bdf8", text: "text-sky-500", icon: "•" },
};

function StatCard({ label, value, hint, tone = "neutral" }) {
  const style = TONE_STYLES[tone];
  return (
    <div
      className="stat-card-accent flex-1 min-w-[150px] bg-white border border-slate-200 rounded-xl p-4 shadow-soft hover:shadow-softHover transition-all duration-200"
      style={{ "--accent-from": style.from, "--accent-to": style.to }}
    >
      <div className="text-[11px] font-mono uppercase tracking-wide text-slate-400">{label}</div>
      <div className="text-2xl font-semibold mt-1.5 text-slate-800">{value}</div>
      {hint && (
        <div className={`text-xs mt-1 flex items-center gap-1 ${style.text}`}>
          <span>{style.icon}</span>
          <span>{hint}</span>
        </div>
      )}
    </div>
  );
}

export default function Dashboard({ propertyId }) {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const { authFetch } = useAuth();

  const fetchStats = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (propertyId) params.set("propertyId", propertyId);
      const res = await authFetch(`${API_BASE}/dashboard/stats?${params.toString()}`);
      if (!res.ok) throw new Error(`Server returned ${res.status}`);
      setStats(await res.json());
    } catch (err) {
      setError(err.message || "Couldn't load dashboard stats.");
    } finally {
      setLoading(false);
    }
  }, [propertyId, authFetch]);

  useEffect(() => {
    fetchStats();
  }, [fetchStats]);

  if (loading) return <p className="text-sm text-slate-400 p-5">Loading dashboard…</p>;
  if (error) {
    return (
      <div className="p-5 text-sm text-rose-600 bg-rose-50 border border-rose-200 rounded-lg flex items-center justify-between max-w-md">
        <span>{error}</span>
        <button onClick={fetchStats} className="underline text-xs">
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="p-5 animate-fade-in">
      <AffirmationBanner />
      <h1 className="text-2xl font-semibold mb-1 gradient-heading">Dashboard</h1>
      <p className="text-sm text-slate-500 mb-5">Portfolio snapshot as of today</p>
      <div className="flex flex-wrap gap-3">
        <StatCard label="Occupancy" value={`${stats.occupancyPct}%`} tone="up" />
        <StatCard
          label="Revenue"
          value={`$${stats.monthlyRevenue.toLocaleString()}`}
          hint="from occupied units"
          tone="up"
        />
        <StatCard label="Vacancies" value={stats.vacantUnits} tone={stats.vacantUnits > 0 ? "down" : "up"} />
        <StatCard
          label="Open tickets"
          value={stats.openTickets}
          hint={stats.urgentTickets > 0 ? `${stats.urgentTickets} urgent` : undefined}
          tone={stats.urgentTickets > 0 ? "down" : "neutral"}
        />
        <StatCard
          label="Inspections due"
          value={stats.inspectionsDue}
          hint="no inspection in past year"
          tone={stats.inspectionsDue > 0 ? "down" : "up"}
        />
      </div>
    </div>
  );
}
