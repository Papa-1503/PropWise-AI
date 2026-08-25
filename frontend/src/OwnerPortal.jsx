import { useState, useEffect, useCallback } from "react";
import { useAuth } from "./AuthContext";
import Avatar from "./Avatar";
import { LayoutDashboard, FileText, Receipt, Building2, DoorOpen, Wrench } from "lucide-react";
import { API_BASE } from "./config";

/**
 * OwnerPortal
 *
 * The entire owner-facing experience — separate from both the staff and
 * tenant interfaces, since an owner's needs are fundamentally different
 * (financial visibility into what they own, not day-to-day operations).
 *
 * Backend already existed and worked (routers/owners.py: /me/dashboard,
 * /me/statements, /me/tax-summary) — this was purely a missing frontend.
 * Before this component existed, an owner logging in fell into the
 * tenant branch of the old binary role check and saw a broken interface
 * (a header reading "Unit —", tenant-only tabs that didn't apply to them).
 */

const TABS = [
  { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
  { id: "statements", label: "Statements", icon: Receipt },
  { id: "tax", label: "Tax Summary", icon: FileText },
];

function StatCard({ label, value, tone = "default" }) {
  const toneClass = {
    default: "text-slate-900",
    good: "text-emerald-600",
    warn: "text-amber-600",
  }[tone];
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4">
      <p className="text-xs text-slate-500">{label}</p>
      <p className={`text-2xl font-semibold mt-1 ${toneClass}`}>{value}</p>
    </div>
  );
}

function OwnerDashboardView() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const { authFetch } = useAuth();

  useEffect(() => {
    (async () => {
      try {
        const res = await authFetch(`${API_BASE}/owners/me/dashboard`);
        if (!res.ok) throw new Error("Couldn't load your dashboard");
        setData(await res.json());
      } catch (err) {
        setError(err.message);
      }
    })();
  }, [authFetch]);

  if (error) return <p className="text-sm text-rose-600">{error}</p>;
  if (!data) return <div className="h-32 bg-slate-100 rounded-xl animate-pulse" />;

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
      <StatCard label="Properties" value={data.propertyCount} />
      <StatCard label="Total Units" value={data.unitCount} />
      <StatCard
        label="Occupancy Rate"
        value={`${data.occupancyRate}%`}
        tone={data.occupancyRate >= 90 ? "good" : data.occupancyRate >= 75 ? "default" : "warn"}
      />
      <StatCard label="Occupied Units" value={data.occupiedUnits} />
      <StatCard label="Vacant Units" value={data.vacantUnits} tone={data.vacantUnits > 0 ? "warn" : "default"} />
      <StatCard
        label="Open Maintenance"
        value={data.openMaintenanceCount}
        tone={data.openMaintenanceCount > 0 ? "warn" : "good"}
      />
    </div>
  );
}

function OwnerStatementsView() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const { authFetch } = useAuth();

  useEffect(() => {
    (async () => {
      try {
        const res = await authFetch(`${API_BASE}/owners/me/statements`);
        if (!res.ok) throw new Error("Couldn't load your statements");
        setData(await res.json());
      } catch (err) {
        setError(err.message);
      }
    })();
  }, [authFetch]);

  if (error) return <p className="text-sm text-rose-600">{error}</p>;
  if (!data) return <div className="h-32 bg-slate-100 rounded-xl animate-pulse" />;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-3">
        <StatCard label="Total Billed" value={`$${data.totals.totalBilled.toLocaleString()}`} />
        <StatCard label="Total Collected" value={`$${data.totals.totalCollected.toLocaleString()}`} tone="good" />
        <StatCard
          label="Outstanding"
          value={`$${data.totals.outstanding.toLocaleString()}`}
          tone={data.totals.outstanding > 0 ? "warn" : "good"}
        />
      </div>

      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-500 text-xs">
            <tr>
              <th className="text-left px-4 py-2 font-medium">Property</th>
              <th className="text-right px-4 py-2 font-medium">Billed</th>
              <th className="text-right px-4 py-2 font-medium">Collected</th>
              <th className="text-right px-4 py-2 font-medium">Outstanding</th>
              <th className="text-right px-4 py-2 font-medium">Charges</th>
            </tr>
          </thead>
          <tbody>
            {data.properties.map((p) => (
              <tr key={p.propertyId} className="border-t border-slate-100">
                <td className="px-4 py-2.5 font-medium">{p.propertyName}</td>
                <td className="px-4 py-2.5 text-right">${p.totalBilled.toLocaleString()}</td>
                <td className="px-4 py-2.5 text-right text-emerald-600">${p.totalCollected.toLocaleString()}</td>
                <td className={`px-4 py-2.5 text-right ${p.outstanding > 0 ? "text-amber-600" : ""}`}>
                  ${p.outstanding.toLocaleString()}
                </td>
                <td className="px-4 py-2.5 text-right text-slate-500">{p.chargeCount}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function OwnerTaxSummaryView() {
  const currentYear = new Date().getFullYear();
  const [year, setYear] = useState(currentYear);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const { authFetch } = useAuth();

  const fetchSummary = useCallback(async (y) => {
    setData(null);
    setError(null);
    try {
      const res = await authFetch(`${API_BASE}/owners/me/tax-summary?year=${y}`);
      if (!res.ok) throw new Error("Couldn't load your tax summary");
      setData(await res.json());
    } catch (err) {
      setError(err.message);
    }
  }, [authFetch]);

  useEffect(() => {
    fetchSummary(year);
  }, [year, fetchSummary]);

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <label className="text-sm text-slate-600">Tax year:</label>
        <select
          value={year}
          onChange={(e) => setYear(Number(e.target.value))}
          className="text-sm border border-slate-200 rounded px-2 py-1"
        >
          {[currentYear, currentYear - 1, currentYear - 2].map((y) => (
            <option key={y} value={y}>{y}</option>
          ))}
        </select>
      </div>

      {error && <p className="text-sm text-rose-600">{error}</p>}

      {data && (
        <>
          <StatCard label={`Total Income Collected (${data.year})`} value={`$${data.totalIncomeCollected.toLocaleString()}`} tone="good" />

          <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-slate-500 text-xs">
                <tr>
                  <th className="text-left px-4 py-2 font-medium">Property</th>
                  <th className="text-right px-4 py-2 font-medium">Income Collected</th>
                  <th className="text-right px-4 py-2 font-medium">Payments</th>
                </tr>
              </thead>
              <tbody>
                {data.properties.map((p) => (
                  <tr key={p.propertyId} className="border-t border-slate-100">
                    <td className="px-4 py-2.5 font-medium">{p.propertyName}</td>
                    <td className="px-4 py-2.5 text-right text-emerald-600">${p.totalCollected.toLocaleString()}</td>
                    <td className="px-4 py-2.5 text-right text-slate-500">{p.paymentCount}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <p className="text-xs text-slate-500 bg-slate-50 border border-slate-200 rounded-lg px-3 py-2.5">
            {data.note}
          </p>
        </>
      )}
    </div>
  );
}

export default function OwnerPortal({ user, logout }) {
  const [tab, setTab] = useState("dashboard");

  return (
    <div className="min-h-screen app-bg">
      <header className="bg-gradient-to-r from-indigo-600 via-violet-600 to-fuchsia-600 text-white px-6 py-3 flex items-center justify-between shadow-md">
        <h1 className="font-serif font-bold text-lg">RentFlow AI</h1>
        <div className="flex items-center gap-3 text-sm">
          <div className="flex items-center gap-2">
            <Avatar name={user.name} size={26} />
            <span>{user.name} · Owner</span>
          </div>
          <button onClick={logout} className="text-xs border border-white/30 rounded px-2 py-1 hover:bg-white/10">
            Sign out
          </button>
        </div>
      </header>

      <nav className="flex gap-2 px-6 py-3">
        {TABS.map((t) => {
          const Icon = t.icon;
          return (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`text-sm px-3 py-1.5 rounded-full flex items-center gap-1.5 transition-transform hover:scale-105 hover:-translate-y-0.5 ${
                tab === t.id
                  ? "bg-gradient-to-r from-indigo-600 to-fuchsia-600 text-white shadow-sm"
                  : "bg-white border border-slate-200 text-slate-600"
              }`}
            >
              <Icon size={14} />
              {t.label}
            </button>
          );
        })}
      </nav>

      <main className="px-6 pb-10 max-w-4xl">
        {tab === "dashboard" && <OwnerDashboardView />}
        {tab === "statements" && <OwnerStatementsView />}
        {tab === "tax" && <OwnerTaxSummaryView />}
      </main>
    </div>
  );
}
