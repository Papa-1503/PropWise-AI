import { useState, useEffect, useCallback } from "react";
import { AlertTriangle, MessageSquareHeart } from "lucide-react";
import { useAuth } from "./AuthContext";
import { API_BASE } from "./config";

const RISK_STYLE = {
  high: "bg-rose-50 text-rose-700 border-rose-200",
  medium: "bg-amber-50 text-amber-700 border-amber-200",
  low: "bg-emerald-50 text-emerald-700 border-emerald-200",
};

function CheckInsList({ leaseId }) {
  const { authFetch } = useAuth();
  const [checkins, setCheckins] = useState(null);

  useEffect(() => {
    authFetch(`${API_BASE}/leases/${leaseId}/renewal-checkins`)
      .then((res) => (res.ok ? res.json() : { checkins: [] }))
      .then((data) => setCheckins(data.checkins || []));
  }, [leaseId, authFetch]);

  if (checkins === null) return <p className="text-[11px] text-slate-400 mt-1">Loading responses…</p>;
  if (checkins.length === 0) return <p className="text-[11px] text-slate-400 mt-1">No check-in response yet.</p>;

  return (
    <div className="mt-2 space-y-1.5">
      {checkins.map((c) => (
        <div key={c.id} className="bg-indigo-50/60 border border-indigo-100 rounded-lg px-2.5 py-2 text-[11px]">
          <p className="flex items-center gap-1 text-indigo-700 font-medium mb-0.5">
            <MessageSquareHeart size={11} />
            {new Date(c.respondedAt).toLocaleDateString()}
          </p>
          <p className="text-slate-700">{c.response}</p>
        </div>
      ))}
    </div>
  );
}

/**
 * RenewalRiskPanel — the real "who should I focus renewal outreach on"
 * view, sorted highest-risk first. See backend/renewal_risk_service.py
 * for the full scoring reasoning and honesty caveats (a real,
 * explainable heuristic, not a validated statistical model).
 */
export default function RenewalRiskPanel({ propertyId }) {
  const { authFetch } = useAuth();
  const [leases, setLeases] = useState(null);
  const [error, setError] = useState(null);
  const [expandedId, setExpandedId] = useState(null);

  const fetchRisk = useCallback(async () => {
    setError(null);
    try {
      const params = new URLSearchParams({ windowDays: "90" });
      if (propertyId) params.set("propertyId", propertyId);
      const res = await authFetch(`${API_BASE}/leases/renewal-risk?${params.toString()}`);
      if (!res.ok) throw new Error("Couldn't load renewal risk data.");
      const data = await res.json();
      setLeases(data.leases || []);
    } catch (err) {
      setError(err.message);
    }
  }, [propertyId, authFetch]);

  useEffect(() => {
    fetchRisk();
  }, [fetchRisk]);

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4">
      <div className="flex items-center gap-2 mb-1">
        <AlertTriangle size={15} className="text-amber-500" />
        <h3 className="text-sm font-semibold">Renewal risk — next 90 days</h3>
      </div>
      <p className="text-[11px] text-slate-400 mb-3">
        A real, explainable score from this app's own payment and maintenance history — a decision aid to prioritize outreach, not a validated prediction.
      </p>

      {error && <p className="text-xs text-rose-600 bg-rose-50 border border-rose-200 rounded px-3 py-2">{error}</p>}
      {!error && leases === null && <p className="text-xs text-slate-400">Loading…</p>}
      {!error && leases && leases.length === 0 && (
        <p className="text-xs text-slate-400">No leases expiring in the next 90 days.</p>
      )}

      <div className="space-y-2">
        {leases && leases.map((l) => (
          <div key={l.leaseId} className="border border-slate-100 rounded-lg p-3">
            <button
              onClick={() => setExpandedId(expandedId === l.leaseId ? null : l.leaseId)}
              className="w-full flex items-center justify-between text-left"
            >
              <div>
                <p className="text-sm font-medium">
                  Unit {l.unitId} {l.residentName && <span className="text-slate-400 font-normal">— {l.residentName}</span>}
                </p>
                <p className="text-[11px] text-slate-400">{l.daysUntilExpiry} days until lease end</p>
              </div>
              <span className={`text-[11px] font-mono uppercase px-2 py-0.5 rounded-full border shrink-0 ${RISK_STYLE[l.riskLevel]}`}>
                {l.riskLevel} · {l.score}
              </span>
            </button>

            {expandedId === l.leaseId && (
              <div className="mt-2.5 pt-2.5 border-t border-slate-100 space-y-1.5">
                {l.factors.map((f) => (
                  <div key={f.name} className="text-[11px]">
                    <div className="flex items-center justify-between text-slate-600">
                      <span>{f.name}</span>
                      <span className="text-slate-400">{f.points}/{f.maxPoints}</span>
                    </div>
                    <p className="text-slate-400">{f.detail}</p>
                  </div>
                ))}
                <CheckInsList leaseId={l.leaseId} />
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
