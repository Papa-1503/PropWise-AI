import { useState, useEffect, useCallback } from "react";
import { useAuth } from "./AuthContext";
import { API_BASE } from "./config";


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
