import { useState, useEffect, useCallback } from "react";
import { useAuth } from "./AuthContext";

const API_BASE = "/api";

/**
 * MaintenanceTrendAlert
 *
 * Replaces the scripted "HVAC Repairs Increasing" example from the
 * mockup with real rolling-window trend detection — see the docstring
 * in routers/dashboard.py for exactly how "increasing" is defined.
 */
export default function MaintenanceTrendAlert({ propertyId }) {
  const [trends, setTrends] = useState([]);
  const [loading, setLoading] = useState(true);
  const [schedulingCategory, setSchedulingCategory] = useState(null);
  const [scheduled, setScheduled] = useState({});
  const { authFetch } = useAuth();

  const fetchTrends = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (propertyId) params.set("propertyId", propertyId);
      const res = await authFetch(`${API_BASE}/dashboard/maintenance-trends?${params.toString()}`);
      if (res.ok) {
        const data = await res.json();
        setTrends(data.trends || []);
      }
    } finally {
      setLoading(false);
    }
  }, [propertyId, authFetch]);

  useEffect(() => {
    fetchTrends();
  }, [fetchTrends]);

  async function handleSchedule(category) {
    setSchedulingCategory(category);
    try {
      const params = new URLSearchParams();
      if (propertyId) params.set("propertyId", propertyId);
      const res = await authFetch(
        `${API_BASE}/dashboard/maintenance-trends/${category}/schedule-inspection?${params.toString()}`,
        { method: "POST" }
      );
      if (res.ok) {
        setScheduled((prev) => ({ ...prev, [category]: true }));
      }
    } finally {
      setSchedulingCategory(null);
    }
  }

  if (loading) return null;
  if (trends.length === 0) return null; // no fabricated alert when nothing real is trending

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4">
      <h3 className="text-sm font-semibold mb-3">Maintenance trends</h3>
      <div className="space-y-3">
        {trends.map((t) => (
          <div key={t.category} className="border border-amber-200 bg-amber-50 rounded-lg p-3">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium capitalize">⚠ {t.category} repairs increasing</span>
            </div>
            <p className="text-xs text-slate-600 mt-1">
              {t.recentCount} in the last 30 days vs {t.priorCount} the 30 days before
              {t.pctChange !== null && ` (+${t.pctChange}%)`}
            </p>
            <button
              onClick={() => handleSchedule(t.category)}
              disabled={schedulingCategory === t.category || scheduled[t.category]}
              className="text-xs font-semibold bg-slate-900 disabled:bg-slate-300 text-white px-3 py-1.5 rounded-lg mt-2"
            >
              {scheduled[t.category]
                ? "Added to AI Actions"
                : schedulingCategory === t.category
                ? "Scheduling…"
                : "Schedule preventive inspection"}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
