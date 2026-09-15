import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Sparkles, ArrowRight, TrendingUp, TrendingDown, AlertTriangle, Wrench, Zap } from "lucide-react";
import { useAuth } from "./AuthContext";
import { API_BASE } from "./config";

/**
 * CommandCenter
 *
 * Added directly in response to real product-review feedback: "make
 * the AI the star of the show... the next evolution should prove the
 * platform can think, prioritize, and drive actions better than a
 * busy property manager can on their own." Sits at the very top of
 * the dashboard, above PortfolioHealthHeader - the first thing staff
 * see, a real "what needs your attention today" digest instead of a
 * passive stats header alone.
 *
 * Every figure comes straight from GET /api/dashboard/command-center
 * (routers/dashboard.py) - 4 real, existing data sources (renewal
 * risk, delinquency, urgent maintenance, pending AI actions), never a
 * fabricated number. Maintenance items show no dollar figure at all
 * rather than a guessed one, since no honest cost-of-inaction model
 * exists for that yet.
 *
 * DELIBERATE DEVIATION from the raw feedback's mockup: no one-click
 * "Approve All" button. Every other agentic feature built this
 * session (the collections copilot, renewal incentives) requires
 * real, explicit per-item human confirmation before anything
 * consequential happens - this digest surfaces priorities and links
 * to the real panel where staff review full context and act, rather
 * than adding a bulk-execute bypass around those existing, safer
 * flows.
 */

const ITEM_ICONS = {
  renewal_risk: TrendingDown,
  delinquent: AlertTriangle,
  maintenance_urgent: Wrench,
  pending_ai_action: Zap,
};

function greetingForHour(hour) {
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

export default function CommandCenter({ propertyId, userName }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const { authFetch } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    setLoading(true);
    const params = new URLSearchParams();
    if (propertyId) params.set("propertyId", propertyId);
    authFetch(`${API_BASE}/dashboard/command-center?${params.toString()}`)
      .then((res) => (res.ok ? res.json() : null))
      .then(setData)
      .finally(() => setLoading(false));
  }, [propertyId, authFetch]);

  if (loading) return <div className="h-32 bg-slate-100 rounded-xl animate-pulse mb-5" />;
  if (!data || data.items.length === 0) return null; // genuinely nothing urgent - no empty digest shown

  const greeting = greetingForHour(new Date().getHours());

  return (
    <div className="bg-gradient-to-br from-indigo-600 via-violet-600 to-fuchsia-600 text-white rounded-xl p-5 mb-5 shadow-lg">
      <div className="flex items-center gap-2 mb-1">
        <Sparkles size={18} />
        <h2 className="text-lg font-serif font-bold">
          {greeting}{userName ? `, ${userName}` : ""}
        </h2>
      </div>
      {data.totalQuantifiedImpact > 0 && (
        <p className="text-white/80 text-sm mb-4">
          Revenue at stake today: <span className="font-semibold text-white">${data.totalQuantifiedImpact.toLocaleString()}</span>
        </p>
      )}
      <p className="text-xs font-mono uppercase tracking-wide text-white/60 mb-2">Today I'd focus on</p>
      <div className="space-y-2">
        {data.items.map((item, i) => {
          const Icon = ITEM_ICONS[item.type] || Sparkles;
          return (
            <button
              key={item.type}
              onClick={() => navigate(item.link)}
              className="w-full flex items-center gap-3 bg-white/10 hover:bg-white/20 rounded-lg px-3.5 py-2.5 text-left transition-colors"
            >
              <span className="w-6 h-6 rounded-full bg-white/15 flex items-center justify-center shrink-0 text-xs font-bold">
                {i + 1}
              </span>
              <Icon size={15} className="shrink-0 text-white/70" />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium truncate">{item.title}</p>
                <p className="text-xs text-white/60 truncate">{item.detail}</p>
              </div>
              {item.dollarImpact != null && (
                <span className="text-sm font-semibold shrink-0">${item.dollarImpact.toLocaleString()}</span>
              )}
              <ArrowRight size={14} className="shrink-0 text-white/50" />
            </button>
          );
        })}
      </div>
    </div>
  );
}
