import { useState, useEffect, useCallback } from "react";
import { useAuth } from "./AuthContext";
import { API_BASE } from "./config";


export default function OccupancyInsight({ propertyId }) {
  const [insight, setInsight] = useState(null);
  const [loading, setLoading] = useState(true);
  const { authFetch } = useAuth();

  const fetchInsight = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (propertyId) params.set("propertyId", propertyId);
      const res = await authFetch(`${API_BASE}/ai/actions/insights/occupancy?${params.toString()}`);
      if (res.ok) setInsight(await res.json());
    } finally {
      setLoading(false);
    }
  }, [propertyId, authFetch]);

  useEffect(() => {
    fetchInsight();
  }, [fetchInsight]);

  if (loading) return <div className="h-40 bg-slate-100 rounded-xl animate-pulse" />;
  if (!insight || insight.totalVacantUnits === 0) return null;

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5">
      <h2 className="text-lg font-semibold mb-1">Why is occupancy dropping?</h2>
      <p className="text-xs text-slate-500 mb-3">
        {insight.totalVacantUnits} of {insight.totalUnits} units vacant ({insight.vacancyRatePct}%)
      </p>

      {insight.primaryCause && (
        <div className="bg-rose-50 border border-rose-200 rounded-lg p-3 mb-3">
          <div className="text-xs font-mono uppercase text-rose-700 tracking-wide">Primary cause</div>
          <div className="text-sm font-semibold mt-0.5">{insight.primaryCause.name}</div>
          <div className="text-xs text-slate-600 mt-0.5">
            {insight.primaryCause.vacantCount} vacant unit{insight.primaryCause.vacantCount !== 1 ? "s" : ""}: {insight.primaryCause.vacantUnitIds.join(", ")}
          </div>
        </div>
      )}

      {insight.averageDaysVacant === null && (
        <p className="text-[10px] text-slate-400 italic mb-3">
          Average days vacant isn't available yet — this requires tracking when each unit became vacant.
        </p>
      )}

      {insight.recommendedActions?.length > 0 && (
        <>
          <div className="text-xs font-mono uppercase text-slate-500 tracking-wide mb-1.5">Recommended actions</div>
          <ol className="text-sm space-y-1 list-decimal list-inside">
            {insight.recommendedActions.map((a, i) => (
              <li key={i}>{a}</li>
            ))}
          </ol>
        </>
      )}
    </div>
  );
}
