import { useState, useEffect, useCallback } from "react";
import { useAuth } from "./AuthContext";

const API_BASE = "/api";

/**
 * ConfidenceDistribution
 *
 * The mockup shows static confidence bars (95%, 70%, 45%). This version
 * pulls the REAL confidence values from currently-suggested AI actions
 * and shows each one individually — no synthetic buckets standing in
 * for data that doesn't exist.
 */
export default function ConfidenceDistribution({ propertyId }) {
  const [actions, setActions] = useState([]);
  const [loading, setLoading] = useState(true);
  const { authFetch } = useAuth();

  const fetchActions = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ status: "suggested" });
      if (propertyId) params.set("propertyId", propertyId);
      const res = await authFetch(`${API_BASE}/ai/actions?${params.toString()}`);
      if (res.ok) {
        const data = await res.json();
        setActions((data.actions || []).sort((a, b) => b.confidence - a.confidence));
      }
    } finally {
      setLoading(false);
    }
  }, [propertyId, authFetch]);

  useEffect(() => {
    fetchActions();
  }, [fetchActions]);

  if (loading) return <div className="h-32 bg-slate-100 rounded-xl animate-pulse" />;

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4">
      <h3 className="text-sm font-semibold mb-3">Confidence</h3>
      {actions.length === 0 ? (
        <p className="text-xs text-slate-400">No pending recommendations right now.</p>
      ) : (
        <div className="space-y-2">
          {actions.map((a) => (
            <div key={a.id} className="flex items-center gap-2">
              <span className="text-xs text-slate-600 truncate flex-1" title={a.title}>
                {a.title}
              </span>
              <div className="w-20 h-1.5 bg-slate-200 rounded-full overflow-hidden">
                <div className="h-full bg-slate-900" style={{ width: `${a.confidence}%` }} />
              </div>
              <span className="text-[11px] font-mono text-slate-500 w-8 text-right">{a.confidence}%</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
