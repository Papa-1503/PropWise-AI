import { useState } from "react";
import { useAuth } from "./AuthContext";
import { Droplets, AlertTriangle, Check } from "lucide-react";
import { API_BASE } from "./config";

/**
 * RubsBilling
 *
 * Real frontend for backend/routers/rubs.py - allocates a real
 * utility bill across a property's occupied units by a real, honest
 * method (square footage, bedroom count, or equal split). Always
 * previews the real allocation before generating actual charges - the
 * backend's own /preview and /generate endpoints share identical
 * logic, so a preview genuinely reflects what /generate will create,
 * not an approximation.
 */
export default function RubsBilling({ propertyId }) {
  const [utilityType, setUtilityType] = useState("water");
  const [totalAmount, setTotalAmount] = useState("");
  const [billingPeriod, setBillingPeriod] = useState(() => new Date().toISOString().slice(0, 7));
  const [allocationMethod, setAllocationMethod] = useState("equalSplit");
  const [dueDate, setDueDate] = useState("");
  const [preview, setPreview] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [generated, setGenerated] = useState(null);
  const { authFetch } = useAuth();

  function buildPayload() {
    return {
      propertyId,
      utilityType,
      totalAmount: Number(totalAmount),
      billingPeriod,
      allocationMethod,
      dueDate,
    };
  }

  async function handlePreview() {
    setLoading(true);
    setError(null);
    setGenerated(null);
    try {
      const res = await authFetch(`${API_BASE}/rubs/preview`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildPayload()),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Couldn't compute the allocation.");
      setPreview(data);
    } catch (err) {
      setError(err.message);
      setPreview(null);
    } finally {
      setLoading(false);
    }
  }

  async function handleGenerate() {
    setLoading(true);
    setError(null);
    try {
      const res = await authFetch(`${API_BASE}/rubs/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildPayload()),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Couldn't generate the charges.");
      setGenerated(data);
      setPreview(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  const canSubmit = propertyId && totalAmount && billingPeriod && dueDate;

  return (
    <div className="max-w-2xl mx-auto">
      <div className="flex items-center gap-2 mb-3">
        <Droplets size={18} className="text-indigo-600" />
        <h2 className="text-lg font-semibold">RUBS — Utility Billing</h2>
      </div>

      {!propertyId && (
        <div className="text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded-lg p-3 mb-3">
          Select a specific building above to allocate a utility bill — RUBS needs one real property, not "All Buildings."
        </div>
      )}

      <div className="bg-white border border-slate-200 rounded-xl p-4 space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs font-medium text-slate-600">Utility type</label>
            <select
              value={utilityType}
              onChange={(e) => setUtilityType(e.target.value)}
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm mt-1"
            >
              <option value="water">Water</option>
              <option value="sewer">Sewer</option>
              <option value="trash">Trash</option>
              <option value="gas">Gas</option>
              <option value="electric">Electric</option>
            </select>
          </div>
          <div>
            <label className="text-xs font-medium text-slate-600">Billing period</label>
            <input
              type="month"
              value={billingPeriod}
              onChange={(e) => setBillingPeriod(e.target.value)}
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm mt-1"
            />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs font-medium text-slate-600">Total bill amount ($)</label>
            <input
              type="number"
              min="0"
              step="0.01"
              value={totalAmount}
              onChange={(e) => setTotalAmount(e.target.value)}
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm mt-1"
            />
          </div>
          <div>
            <label className="text-xs font-medium text-slate-600">Due date</label>
            <input
              type="date"
              value={dueDate}
              onChange={(e) => setDueDate(e.target.value)}
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm mt-1"
            />
          </div>
        </div>

        <div>
          <label className="text-xs font-medium text-slate-600">Allocation method</label>
          <select
            value={allocationMethod}
            onChange={(e) => setAllocationMethod(e.target.value)}
            className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm mt-1"
          >
            <option value="equalSplit">Equal split (no per-unit data needed)</option>
            <option value="squareFootage">By square footage</option>
            <option value="bedroomCount">By bedroom count</option>
          </select>
        </div>

        {error && <p className="text-sm text-rose-600" role="alert">{error}</p>}

        <button
          onClick={handlePreview}
          disabled={!canSubmit || loading}
          className="w-full bg-slate-900 text-white rounded-lg py-2 text-sm font-semibold hover:bg-slate-800 disabled:opacity-50"
        >
          {loading && !preview ? "Computing..." : "Preview allocation"}
        </button>
      </div>

      {preview && (
        <div className="bg-white border border-slate-200 rounded-xl p-4 mt-3">
          <h3 className="text-sm font-semibold mb-2">Preview — {preview.allocations?.length || 0} units</h3>

          {preview.warnings?.length > 0 && (
            <div className="flex items-start gap-2 bg-amber-50 border border-amber-200 rounded-lg p-2.5 mb-3 text-xs text-amber-800">
              <AlertTriangle size={14} className="shrink-0 mt-0.5" />
              <div>{preview.warnings.map((w, i) => <p key={i}>{w}</p>)}</div>
            </div>
          )}

          <div className="max-h-60 overflow-y-auto space-y-1">
            {preview.allocations?.map((a) => (
              <div key={a.unitId} className="flex justify-between text-sm py-1 border-b border-slate-50">
                <span>Unit {a.unitId} <span className="text-slate-400 text-xs">({a.basis})</span></span>
                <span className="font-medium">${a.amount.toFixed(2)}</span>
              </div>
            ))}
          </div>

          <button
            onClick={handleGenerate}
            disabled={loading}
            className="w-full mt-3 bg-indigo-600 text-white rounded-lg py-2 text-sm font-semibold hover:bg-indigo-700 disabled:opacity-50"
          >
            {loading ? "Generating..." : "Generate real charges"}
          </button>
        </div>
      )}

      {generated && (
        <div className="flex items-center gap-2 bg-emerald-50 border border-emerald-200 rounded-lg p-3 mt-3 text-sm text-emerald-700">
          <Check size={16} />
          {generated.chargesCreated} real charges created and added to residents' accounts.
        </div>
      )}
    </div>
  );
}
