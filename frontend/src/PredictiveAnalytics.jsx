import { useState, useEffect, useCallback } from "react";
import { useAuth } from "./AuthContext";
import EmptyState from "./EmptyState";
import { TrendingUp } from "lucide-react";
import { API_BASE } from "./config";

export default function PredictiveAnalytics({ propertyId }) {
  const [tab, setTab] = useState("churn");
  const [churnLeases, setChurnLeases] = useState([]);
  const [vacancyRows, setVacancyRows] = useState([]);
  const [vacancyNote, setVacancyNote] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const { authFetch } = useAuth();

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (propertyId) params.set("propertyId", propertyId);
      const [churnRes, vacancyRes] = await Promise.all([
        authFetch(`${API_BASE}/predictive/churn-risk?${params.toString()}`),
        authFetch(`${API_BASE}/predictive/vacancy-forecast?${params.toString()}`),
      ]);
      if (!churnRes.ok || !vacancyRes.ok) throw new Error("Couldn't load predictive analytics.");
      const churnData = await churnRes.json();
      const vacancyData = await vacancyRes.json();
      setChurnLeases(churnData.leases || []);
      setVacancyRows(vacancyData.rows || []);
      setVacancyNote(vacancyData.note || "");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [propertyId, authFetch]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  function riskColor(score) {
    if (score >= 50) return "text-rose-600 bg-rose-50 border-rose-200";
    if (score >= 25) return "text-amber-600 bg-amber-50 border-amber-200";
    return "text-emerald-600 bg-emerald-50 border-emerald-200";
  }

  return (
    <div className="max-w-2xl mx-auto">
      <div className="flex items-center gap-2 mb-3">
        <TrendingUp size={18} className="text-indigo-600" />
        <h2 className="text-lg font-semibold">Predictive Analytics</h2>
      </div>

      <div className="flex gap-1.5 mb-3">
        {["churn", "vacancy"].map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`text-xs font-medium px-2.5 py-1 rounded-full border ${
              tab === t ? "bg-indigo-600 text-white border-indigo-600" : "bg-white text-slate-600 border-slate-200"
            }`}
          >
            {t === "churn" ? "Churn Risk" : "Vacancy Pattern"}
          </button>
        ))}
      </div>

      {loading && <div className="text-sm text-slate-500">Loading...</div>}
      {error && <div className="text-sm text-rose-600 bg-rose-50 border border-rose-200 rounded-lg p-3" role="alert">{error}</div>}

      {!loading && !error && tab === "churn" && (
        churnLeases.length === 0 ? (
          <EmptyState icon={TrendingUp} title="No leases to score" subtitle="Every lease may already be renewed." />
        ) : (
          <div className="space-y-2">
            {churnLeases.map((l) => (
              <div key={l.leaseId} className="bg-white border border-slate-200 rounded-lg p-3">
                <div className="flex items-center justify-between mb-1.5">
                  <p className="text-sm font-medium">{l.residentName} — Unit {l.unitId}</p>
                  <span className={`text-xs font-semibold px-2 py-0.5 rounded-full border ${riskColor(l.churnRiskScore)}`}>
                    {l.churnRiskScore}/100
                  </span>
                </div>
                <div className="text-xs text-slate-500 flex flex-wrap gap-x-3 gap-y-0.5">
                  {l.factors.daysToExpiry !== null && <span>{l.factors.daysToExpiry}d to expiry</span>}
                  <span>Renewal: {l.factors.renewalStatus}</span>
                  {l.factors.paymentReliabilityScore !== null && <span>Payment reliability: {l.factors.paymentReliabilityScore}</span>}
                  <span>{l.factors.openTicketCount} open ticket(s)</span>
                </div>
              </div>
            ))}
          </div>
        )
      )}

      {!loading && !error && tab === "vacancy" && (
        <div>
          {vacancyNote && (
            <p className="text-xs text-slate-500 bg-slate-50 border border-slate-200 rounded-lg p-3 mb-3">{vacancyNote}</p>
          )}
          <div className="bg-white border border-slate-200 rounded-xl p-4">
            <div className="space-y-1">
              {vacancyRows.map((r) => (
                <div key={r.monthNumber} className="flex items-center gap-3">
                  <span className="text-sm w-24 shrink-0">{r.month}</span>
                  <div className="flex-1 bg-slate-100 rounded-full h-2 overflow-hidden">
                    <div
                      className="bg-indigo-500 h-full"
                      style={{ width: `${Math.min(100, r.historicalLeaseEndCount * 10)}%` }}
                    />
                  </div>
                  <span className="text-xs text-slate-500 w-6 text-right">{r.historicalLeaseEndCount}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
