import { useState, useEffect } from "react";
import { useAuth } from "./AuthContext";
import { API_BASE } from "./config";

/**
 * RecentActivity
 *
 * Split into its own file (Aug 25, 2026) rather than living inside
 * Dashboard.jsx — Dashboard now uses recharts for real chart
 * visualizations, which roughly doubled the app's bundle size and is
 * lazy-loaded as a result. This component doesn't touch recharts at
 * all and is used in the dashboard sidebar regardless, so it stays
 * eagerly loaded rather than being pulled into that same lazy chunk.
 */

const EVENT_ICON = { payment: "💰", maintenance: "🔧", lease: "📄" };

function timeAgo(iso) {
  const diffMs = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

export default function RecentActivity({ propertyId }) {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const { authFetch } = useAuth();

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const params = new URLSearchParams();
        if (propertyId) params.set("propertyId", propertyId);
        const res = await authFetch(`${API_BASE}/dashboard/recent-activity?${params.toString()}`);
        if (res.ok && !cancelled) {
          const data = await res.json();
          setEvents(data.events || []);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [propertyId, authFetch]);

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4">
      <h3 className="text-sm font-semibold text-slate-800 mb-3">Recent Activity</h3>
      {loading ? (
        <p className="text-xs text-slate-400">Loading…</p>
      ) : events.length === 0 ? (
        <p className="text-xs text-slate-400">Nothing recent to show.</p>
      ) : (
        <div className="space-y-2.5">
          {events.map((e, i) => (
            <div key={i} className="flex items-start gap-2.5">
              <span className="text-sm shrink-0">{EVENT_ICON[e.type] || "•"}</span>
              <div className="min-w-0">
                <p className="text-xs text-slate-700 leading-snug">{e.text}</p>
                <p className="text-[10px] text-slate-400 mt-0.5">{timeAgo(e.timestamp)}</p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
