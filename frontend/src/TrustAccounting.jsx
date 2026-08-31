import { useState, useEffect, useCallback } from "react";
import { useAuth } from "./AuthContext";
import { Landmark, AlertTriangle } from "lucide-react";
import { API_BASE } from "./config";

/**
 * TrustAccounting
 *
 * Real frontend for backend/routers/trust_accounting.py. Shows the
 * real per-property trust-fund balance (computed from bank lines
 * staff have classified as fundType="trust") and the real commingling
 * check. The disclaimer from the backend is shown prominently and
 * verbatim, not paraphrased away - this genuinely isn't a substitute
 * for real trust-accounting compliance.
 */
export default function TrustAccounting({ propertyId }) {
  const [balances, setBalances] = useState([]);
  const [flags, setFlags] = useState([]);
  const [disclaimer, setDisclaimer] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const { authFetch } = useAuth();

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (propertyId) params.set("propertyId", propertyId);
      const [balRes, flagRes] = await Promise.all([
        authFetch(`${API_BASE}/trust-accounting/balance?${params.toString()}`),
        authFetch(`${API_BASE}/trust-accounting/commingling-check?${params.toString()}`),
      ]);
      if (!balRes.ok || !flagRes.ok) throw new Error("Couldn't load trust accounting data.");
      const balData = await balRes.json();
      const flagData = await flagRes.json();
      setBalances(balData.rows || []);
      setDisclaimer(balData.disclaimer || "");
      setFlags(flagData.flags || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [propertyId, authFetch]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return (
    <div className="max-w-2xl mx-auto">
      <div className="flex items-center gap-2 mb-3">
        <Landmark size={18} className="text-indigo-600" />
        <h2 className="text-lg font-semibold">Trust Accounting</h2>
      </div>

      {disclaimer && (
        <div className="text-xs text-slate-500 bg-slate-50 border border-slate-200 rounded-lg p-3 mb-3">
          {disclaimer}
        </div>
      )}

      {loading && <div className="text-sm text-slate-500">Loading...</div>}
      {error && <div className="text-sm text-rose-600 bg-rose-50 border border-rose-200 rounded-lg p-3" role="alert">{error}</div>}

      {!loading && !error && flags.length > 0 && (
        <div className="bg-rose-50 border border-rose-200 rounded-xl p-4 mb-3">
          <div className="flex items-center gap-2 mb-2">
            <AlertTriangle size={16} className="text-rose-600" />
            <h3 className="text-sm font-semibold text-rose-700">Flagged for review ({flags.length})</h3>
          </div>
          <div className="space-y-2">
            {flags.map((f) => (
              <div key={f.propertyId} className="text-sm">
                <p className="font-medium text-rose-800">
                  {f.propertyId}: ${f.trustBalance.toFixed(2)}
                </p>
                <p className="text-xs text-rose-600">{f.concern}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {!loading && !error && (
        <div className="bg-white border border-slate-200 rounded-xl p-4">
          <h3 className="text-sm font-semibold mb-2">Trust fund balance by property</h3>
          {balances.length === 0 ? (
            <p className="text-sm text-slate-400">
              No bank lines classified as trust funds yet — mark a reconciliation line's fund type as "trust" to see it here.
            </p>
          ) : (
            <div className="space-y-1">
              {balances.map((b) => (
                <div key={b.propertyId} className="flex justify-between text-sm py-1.5 border-b border-slate-50">
                  <span>{b.propertyId} <span className="text-slate-400 text-xs">({b.lineCount} lines)</span></span>
                  <span className={`font-medium ${b.trustBalance < 0 ? "text-rose-600" : "text-slate-800"}`}>
                    ${b.trustBalance.toFixed(2)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
