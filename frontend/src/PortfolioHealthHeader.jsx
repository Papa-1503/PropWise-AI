import { useState, useEffect, useCallback } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
import { useAuth } from "./AuthContext";
import { API_BASE } from "./config";

/**
 * NOISummary
 *
 * Added in direct response to real product-review feedback: "the
 * first number on many investor dashboards would be NOI... I would
 * put it near the top." Sits directly above the existing health-
 * score header, the real, top-of-dashboard spot. All three real
 * figures come straight from GET /api/dashboard/noi
 * (routers/dashboard.py) - noiThisMonth is real, already-collected
 * revenue minus real, categorized expenses; noiAtRisk reuses the
 * exact same revenue-at-risk figure the health score below already
 * shows (never a second, diverging definition); noiProjectedThisMonth
 * is an honestly-labeled ESTIMATE, and shows nothing rather than a
 * fabricated number when there isn't yet enough real expense history
 * to base a projection on (hasEnoughHistoryForProjection).
 */
function NOISummary({ propertyId }) {
  const [noi, setNoi] = useState(null);
  const [expanded, setExpanded] = useState(null); // 'this' | 'risk' | 'projected' | null
  const { authFetch } = useAuth();

  useEffect(() => {
    const params = new URLSearchParams();
    if (propertyId) params.set("propertyId", propertyId);
    authFetch(`${API_BASE}/dashboard/noi?${params.toString()}`)
      .then((res) => (res.ok ? res.json() : null))
      .then(setNoi)
      .catch(() => {});
  }, [propertyId, authFetch]);

  if (!noi) return null;

  const toggle = (key) => setExpanded((cur) => (cur === key ? null : key));
  const fmt = (n) => (n < 0 ? `-$${Math.abs(n).toLocaleString()}` : `$${n.toLocaleString()}`);

  return (
    <div className="bg-white/5 border border-white/10 rounded-lg p-4 mb-4">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <button onClick={() => toggle("this")} className="text-left">
          <div className="text-[10px] font-mono uppercase tracking-wide text-white/50 flex items-center gap-1">
            NOI This Month {expanded === "this" ? <ChevronUp size={10} /> : <ChevronDown size={10} />}
          </div>
          <div className={`text-2xl font-bold mt-0.5 ${noi.noiThisMonth < 0 ? "text-rose-300" : "text-white"}`}>
            {fmt(noi.noiThisMonth)}
          </div>
        </button>
        <button onClick={() => toggle("risk")} className="text-left">
          <div className="text-[10px] font-mono uppercase tracking-wide text-white/50 flex items-center gap-1">
            NOI At Risk {expanded === "risk" ? <ChevronUp size={10} /> : <ChevronDown size={10} />}
          </div>
          <div className="text-2xl font-bold mt-0.5 text-amber-300">{fmt(noi.noiAtRisk)}</div>
        </button>
        <button onClick={() => toggle("projected")} disabled={!noi.hasEnoughHistoryForProjection} className="text-left disabled:cursor-default">
          <div className="text-[10px] font-mono uppercase tracking-wide text-white/50 flex items-center gap-1">
            NOI Projected (Est.) {noi.hasEnoughHistoryForProjection && (expanded === "projected" ? <ChevronUp size={10} /> : <ChevronDown size={10} />)}
          </div>
          <div className="text-2xl font-bold mt-0.5 text-white/90">
            {noi.hasEnoughHistoryForProjection ? fmt(noi.noiProjectedThisMonth) : <span className="text-sm font-normal text-white/40 italic">not enough history yet</span>}
          </div>
        </button>
      </div>

      {expanded === "this" && (
        <p className="text-[11px] text-white/60 mt-3 pt-3 border-t border-white/10">
          ${noi.revenueCollectedThisMonth.toLocaleString()} collected across {noi.revenueChargeCount} payment{noi.revenueChargeCount === 1 ? "" : "s"} so far this month, minus ${noi.expensesThisMonth.toLocaleString()} in {noi.expenseLineCount} categorized expense{noi.expenseLineCount === 1 ? "" : "s"}. A real, partial-month figure — will keep changing as the month goes on.
        </p>
      )}
      {expanded === "risk" && (
        <p className="text-[11px] text-white/60 mt-3 pt-3 border-t border-white/10">
          {noi.vacancies} vacant unit{noi.vacancies === 1 ? "" : "s"}, {noi.leaseRenewalsNeeded} lease{noi.leaseRenewalsNeeded === 1 ? "" : "s"} needing renewal attention, and ${noi.delinquentBalance.toLocaleString()} across {noi.delinquentAccounts} delinquent account{noi.delinquentAccounts === 1 ? "" : "s"}. Same figure shown in the health score below.
        </p>
      )}
      {expanded === "projected" && noi.hasEnoughHistoryForProjection && (
        <p className="text-[11px] text-white/60 mt-3 pt-3 border-t border-white/10">
          Estimate only: ${noi.scheduledMonthlyRevenue.toLocaleString()} scheduled full-month rent roll, minus ${noi.projectedExpenses.toLocaleString()} — the real trailing {noi.trailingMonthsUsed}-month average of actual categorized expenses. Not a guarantee.
        </p>
      )}
    </div>
  );
}


export default function PortfolioHealthHeader({ propertyId, userName }) {
  const [health, setHealth] = useState(null);
  const [loading, setLoading] = useState(true);
  const { authFetch } = useAuth();

  const fetchHealth = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (propertyId) params.set("propertyId", propertyId);
      const res = await authFetch(`${API_BASE}/dashboard/health?${params.toString()}`);
      if (res.ok) setHealth(await res.json());
    } finally {
      setLoading(false);
    }
  }, [propertyId, authFetch]);

  useEffect(() => {
    fetchHealth();
  }, [fetchHealth]);

  const greeting = new Date().getHours() < 12 ? "Good morning" : new Date().getHours() < 18 ? "Good afternoon" : "Good evening";

  if (loading) return <div className="h-24 bg-slate-100 rounded-xl animate-pulse" />;
  if (!health) return null;

  const scoreColor = health.healthScore >= 80 ? "text-emerald-600" : health.healthScore >= 60 ? "text-amber-600" : "text-rose-600";

  return (
    <div className="bg-[#14213d] text-white rounded-xl p-5 mb-5">
      <NOISummary propertyId={propertyId} />
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-serif font-bold">{greeting}{userName ? `, ${userName}` : ""}</h1>
          <p className="text-white/60 text-xs mt-0.5">Portfolio snapshot as of today</p>
        </div>
        <div className="flex flex-col items-center">
          <div className="relative w-20 h-20">
            <svg viewBox="0 0 80 80" className="w-20 h-20 -rotate-90">
              <circle cx="40" cy="40" r="34" fill="none" stroke="rgba(255,255,255,0.15)" strokeWidth="7" />
              <circle
                cx="40" cy="40" r="34" fill="none"
                stroke="currentColor" strokeWidth="7" strokeLinecap="round"
                strokeDasharray={2 * Math.PI * 34}
                strokeDashoffset={2 * Math.PI * 34 * (1 - health.healthScore / 100)}
                className={`${scoreColor} transition-all duration-700 ease-out`}
              />
            </svg>
            <div className={`absolute inset-0 flex items-center justify-center text-xl font-bold ${scoreColor}`}>
              {health.healthScore}
            </div>
          </div>
          <div className="text-[10px] font-mono text-white/50 uppercase tracking-wide mt-1">Health Score</div>
        </div>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 mt-5">
        <div>
          <div className="text-[10px] font-mono uppercase tracking-wide text-white/50">Revenue at Risk</div>
          <div className="text-lg font-semibold mt-0.5">${health.revenueAtRisk.toLocaleString()}</div>
        </div>
        <div>
          <div className="text-[10px] font-mono uppercase tracking-wide text-white/50">Vacancies</div>
          <div className="text-lg font-semibold mt-0.5">{health.vacancies}</div>
        </div>
        <div>
          <div className="text-[10px] font-mono uppercase tracking-wide text-white/50">Lease Renewals</div>
          <div className="text-lg font-semibold mt-0.5">{health.leaseRenewalsNeeded}</div>
        </div>
        <div>
          <div className="text-[10px] font-mono uppercase tracking-wide text-white/50">Critical Work Orders</div>
          <div className="text-lg font-semibold mt-0.5">{health.criticalWorkOrders}</div>
        </div>
        {health.delinquentAccounts > 0 && (
          <div>
            <div className="text-[10px] font-mono uppercase tracking-wide text-white/50">Delinquent Accounts</div>
            <div className="text-lg font-semibold mt-0.5">
              {health.delinquentAccounts} <span className="text-xs font-normal text-white/60">(${health.delinquentBalance.toLocaleString()})</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
