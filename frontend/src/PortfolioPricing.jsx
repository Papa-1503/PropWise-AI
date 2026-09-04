import { useState, useEffect, useCallback } from "react";
import { useAuth } from "./AuthContext";
import { API_BASE } from "./config";
import EmptyState from "./EmptyState";
import { Building2, TrendingUp, TrendingDown } from "lucide-react";

/**
 * PortfolioPricing
 *
 * Real cross-building rent comparison, from backend/portfolio_pricing_service.py -
 * "Building 5 is 12% below what the rest of your portfolio charges for
 * comparable units." Pure internal arithmetic (rent per bedroom-count
 * bucket, this building vs. every other), no external market API
 * dependency - distinct from the separate Market Rent Analysis tool,
 * which compares a single unit against the broader local market.
 */

const BEDROOM_LABEL = { 0: "Studio" };
function bedroomLabel(n) {
  return BEDROOM_LABEL[n] || `${n} BR`;
}

export default function PortfolioPricing() {
  const [comparisons, setComparisons] = useState(null);
  const [error, setError] = useState(null);
  const [flaggedOnly, setFlaggedOnly] = useState(true);
  const { authFetch } = useAuth();

  const fetchComparisons = useCallback(async () => {
    setError(null);
    try {
      const res = await authFetch(`${API_BASE}/portfolio-pricing/comparison`);
      if (!res.ok) throw new Error("Couldn't load the pricing comparison.");
      const data = await res.json();
      setComparisons(data.comparisons || []);
    } catch (err) {
      setError(err.message);
    }
  }, [authFetch]);

  useEffect(() => {
    fetchComparisons();
  }, [fetchComparisons]);

  const visible = comparisons ? (flaggedOnly ? comparisons.filter((c) => c.flagged) : comparisons) : [];

  return (
    <div className="max-w-2xl mx-auto p-5 bg-white rounded-xl border border-slate-200">
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-2">
          <Building2 size={18} className="text-slate-500" />
          <h2 className="text-lg font-semibold">Portfolio Pricing</h2>
        </div>
        <button
          onClick={() => setFlaggedOnly((v) => !v)}
          className="text-[11px] px-2.5 py-1 rounded-full border border-slate-200 text-slate-500 hover:border-indigo-300"
        >
          {flaggedOnly ? "Showing gaps ≥5% only" : "Showing all buckets"}
        </button>
      </div>
      <p className="text-xs text-slate-500 mb-4">
        Real average rent per bedroom count, this building vs. every other building in your portfolio with the
        same unit size — computed from actual rent on file, not an external market estimate.
      </p>

      {error && (
        <p role="alert" className="text-sm text-rose-600 bg-rose-50 border border-rose-200 rounded-xl px-4 py-3">
          {error}
        </p>
      )}

      {!error && comparisons === null && <div className="h-32 bg-slate-100 rounded-xl animate-pulse" />}

      {!error && comparisons !== null && visible.length === 0 && (
        <EmptyState
          icon={Building2}
          title={flaggedOnly ? "No gaps of 5% or more right now" : "Not enough data for a comparison yet"}
          subtitle={
            flaggedOnly
              ? "Every building is within 5% of the rest of your portfolio for comparable unit sizes."
              : "Comparisons need at least two buildings with rent set on units of the same bedroom count."
          }
        />
      )}

      {!error && visible.length > 0 && (
        <div className="space-y-2">
          {visible.map((c, i) => {
            const below = c.pctDiff < 0;
            return (
              <div
                key={i}
                className={`border rounded-lg px-3 py-2.5 ${
                  c.flagged
                    ? below
                      ? "bg-amber-50 border-amber-200"
                      : "bg-emerald-50 border-emerald-200"
                    : "bg-slate-50 border-slate-200"
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium">
                    {c.propertyName} · {bedroomLabel(c.bedrooms)}
                  </span>
                  <span
                    className={`flex items-center gap-1 text-xs font-semibold ${
                      below ? "text-amber-700" : c.pctDiff > 0 ? "text-emerald-700" : "text-slate-500"
                    }`}
                  >
                    {below ? <TrendingDown size={13} /> : c.pctDiff > 0 ? <TrendingUp size={13} /> : null}
                    {c.pctDiff > 0 ? "+" : ""}
                    {c.pctDiff}%
                  </span>
                </div>
                <p className="text-xs text-slate-500 mt-1">
                  ${c.propertyAvgRent.toLocaleString()}/mo avg here ({c.unitCount} unit{c.unitCount !== 1 ? "s" : ""}) vs.{" "}
                  ${c.restOfPortfolioAvgRent.toLocaleString()}/mo avg across the rest of your portfolio (
                  {c.restOfPortfolioUnitCount} unit{c.restOfPortfolioUnitCount !== 1 ? "s" : ""})
                </p>
                {c.flagged && below && (
                  <p className="text-[11px] text-amber-700 mt-1">Possible room to raise rent here.</p>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
