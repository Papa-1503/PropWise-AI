import { useState, useEffect, useCallback } from "react";
import { useAuth } from "./AuthContext";
import { API_BASE } from "./config";
import AffirmationBanner from "./AffirmationBanner";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from "recharts";

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

const OCCUPANCY_COLORS = ["#6366f1", "#e2e8f0", "#f59e0b"]; // occupied, vacant, maintenance hold

function OccupancyChart({ occupied, vacant, maintenanceHold }) {
  const total = occupied + vacant + maintenanceHold;
  if (total === 0) return null;
  // All three real statuses shown, not just occupied/vacant — a unit on
  // maintenance hold is neither, and silently leaving it out of the
  // chart means the segments don't actually sum to every real unit.
  const data = [
    { name: "Occupied", value: occupied },
    { name: "Vacant", value: vacant },
    { name: "Maintenance hold", value: maintenanceHold },
  ].filter((d) => d.value > 0);
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4">
      <h3 className="text-sm font-semibold text-slate-800 mb-2">Occupancy</h3>
      <ResponsiveContainer width="100%" height={200}>
        <PieChart>
          <Pie data={data} cx="50%" cy="50%" innerRadius={50} outerRadius={80} paddingAngle={3} dataKey="value">
            {data.map((d, i) => (
              <Cell key={i} fill={OCCUPANCY_COLORS[["Occupied", "Vacant", "Maintenance hold"].indexOf(d.name)]} />
            ))}
          </Pie>
          <Tooltip formatter={(v) => `${v} units`} />
        </PieChart>
      </ResponsiveContainer>
      <div className="flex justify-center flex-wrap gap-4 mt-1 text-xs">
        <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-indigo-500" />Occupied ({occupied})</span>
        <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-slate-200" />Vacant ({vacant})</span>
        {maintenanceHold > 0 && (
          <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-amber-500" />Maintenance hold ({maintenanceHold})</span>
        )}
      </div>
    </div>
  );
}

function RevenueTrendChart({ propertyId }) {
  const [months, setMonths] = useState([]);
  const [loading, setLoading] = useState(true);
  const { authFetch } = useAuth();

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const params = new URLSearchParams();
        if (propertyId) params.set("propertyId", propertyId);
        const res = await authFetch(`${API_BASE}/dashboard/revenue-trend?${params.toString()}`);
        if (res.ok && !cancelled) {
          const data = await res.json();
          setMonths(data.months || []);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [propertyId, authFetch]);

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4">
      <h3 className="text-sm font-semibold text-slate-800 mb-2">Revenue Collected by Month</h3>
      {loading ? (
        <p className="text-xs text-slate-400">Loading…</p>
      ) : months.length === 0 ? (
        <p className="text-xs text-slate-400">Not enough payment history yet.</p>
      ) : (
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={months}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
            <XAxis dataKey="month" tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`} />
            <Tooltip formatter={(v) => `$${v.toLocaleString()}`} />
            <Bar dataKey="collected" fill="#6366f1" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
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

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-5">
        <RevenueTrendChart propertyId={propertyId} />
        <OccupancyChart
          occupied={stats.occupiedUnits ?? 0}
          vacant={stats.vacantUnitsCount ?? 0}
          maintenanceHold={stats.maintenanceHoldUnits ?? 0}
        />
      </div>
    </div>
  );
}
