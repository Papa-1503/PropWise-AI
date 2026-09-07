import { useState, useEffect, useCallback } from "react";
import { useAuth } from "./AuthContext";
import EmptyState from "./EmptyState";
import { Wallet, Plus, X, TrendingUp, TrendingDown } from "lucide-react";
import { API_BASE } from "./config";

/**
 * Budgets
 *
 * The first frontend for the budget-vs-actual feature - the backend
 * (POST/GET/PATCH /api/budgets, GET /api/budgets/report) already
 * existed fully, but nothing in the UI ever called it. Two tabs:
 * real saved budget lines (one per property+category+month), and the
 * real comparison report against actual bank-line spending for a
 * chosen month.
 */

const CATEGORY_OPTIONS = ["maintenance", "utilities", "insurance", "landscaping", "supplies", "administrative", "other"];

function currentPeriod() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

export default function Budgets({ propertyId }) {
  const [tab, setTab] = useState("lines");

  if (!propertyId) {
    return (
      <div className="max-w-2xl mx-auto p-5 bg-white rounded-xl border border-slate-200">
        <h2 className="text-lg font-semibold mb-1">Budgets</h2>
        <p className="text-sm text-slate-500">
          Budgeting is scoped to one building at a time — pick one from the selector in the header first.
        </p>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-lg font-semibold">Budgets</h2>
      </div>
      <div className="flex gap-1.5 mb-3">
        {["lines", "report"].map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`text-xs font-medium px-2.5 py-1 rounded-full border ${
              tab === t ? "bg-indigo-600 text-white border-indigo-600" : "bg-white text-slate-600 border-slate-200"
            }`}
          >
            {t === "lines" ? "Budget Lines" : "Budget vs. Actual"}
          </button>
        ))}
      </div>
      {tab === "lines" ? <BudgetLinesTab propertyId={propertyId} /> : <BudgetReportTab propertyId={propertyId} />}
    </div>
  );
}

function BudgetLinesTab({ propertyId }) {
  const [budgets, setBudgets] = useState([]);
  const [period, setPeriod] = useState(currentPeriod());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showNew, setShowNew] = useState(false);
  const { authFetch } = useAuth();

  const fetchBudgets = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ propertyId, period });
      const res = await authFetch(`${API_BASE}/budgets?${params.toString()}`);
      if (!res.ok) throw new Error("Couldn't load budgets.");
      const data = await res.json();
      setBudgets(data.budgets || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [propertyId, period, authFetch]);

  useEffect(() => {
    fetchBudgets();
  }, [fetchBudgets]);

  return (
    <div>
      <div className="flex items-center gap-2 mb-3">
        <label htmlFor="budget-period" className="text-xs text-slate-500">Month</label>
        <input
          id="budget-period"
          type="month"
          value={period}
          onChange={(e) => setPeriod(e.target.value)}
          className="border border-slate-200 rounded-lg px-2 py-1 text-sm"
        />
      </div>

      <button
        onClick={() => setShowNew(true)}
        className="flex items-center gap-1.5 text-sm font-semibold bg-slate-900 text-white px-3 py-1.5 rounded-lg hover:bg-slate-800 mb-3"
      >
        <Plus size={14} /> New budget line
      </button>

      {loading && <div className="text-sm text-slate-500">Loading...</div>}
      {error && <div className="text-sm text-rose-600 bg-rose-50 border border-rose-200 rounded-lg p-3" role="alert">{error}</div>}

      {!loading && !error && budgets.length === 0 && (
        <EmptyState icon={Wallet} title="No budget lines for this month" subtitle="Set an expected monthly amount per category to track against real spending." />
      )}

      {!loading && !error && budgets.length > 0 && (
        <div className="space-y-2">
          {budgets.map((b) => (
            <div key={b.id} className="bg-white border border-slate-200 rounded-lg p-3 flex items-center justify-between">
              <span className="text-sm font-medium capitalize">{b.category}</span>
              <span className="text-sm text-slate-600">${b.budgetedAmount.toLocaleString()}</span>
            </div>
          ))}
        </div>
      )}

      {showNew && (
        <NewBudgetModal
          propertyId={propertyId}
          period={period}
          onClose={() => setShowNew(false)}
          onSaved={fetchBudgets}
        />
      )}
    </div>
  );
}

function NewBudgetModal({ propertyId, period, onClose, onSaved }) {
  const [category, setCategory] = useState(CATEGORY_OPTIONS[0]);
  const [budgetedAmount, setBudgetedAmount] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const { authFetch } = useAuth();

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      const res = await authFetch(`${API_BASE}/budgets`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ propertyId, category, period, budgetedAmount: Number(budgetedAmount) }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Couldn't save the budget line.");
      onSaved();
      onClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-30 p-4">
      <div className="bg-white rounded-xl p-5 w-full max-w-sm">
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-semibold">New budget line — {period}</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600"><X size={18} /></button>
        </div>
        {error && <p className="text-sm text-rose-600 mb-2" role="alert">{error}</p>}
        <div className="space-y-2">
          <div>
            <label htmlFor="new-budget-category" className="text-xs text-slate-500">Category</label>
            <select
              id="new-budget-category"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm mt-1 capitalize"
            >
              {CATEGORY_OPTIONS.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="new-budget-amount" className="text-xs text-slate-500">Budgeted amount ($)</label>
            <input
              id="new-budget-amount"
              type="number" min="0"
              value={budgetedAmount}
              onChange={(e) => setBudgetedAmount(e.target.value)}
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm mt-1"
            />
          </div>
        </div>
        <button
          onClick={handleSave}
          disabled={saving || !budgetedAmount}
          className="w-full mt-3 bg-slate-900 text-white rounded-lg py-2 text-sm font-semibold hover:bg-slate-800 disabled:opacity-50"
        >
          {saving ? "Saving..." : "Save budget line"}
        </button>
      </div>
    </div>
  );
}

function BudgetReportTab({ propertyId }) {
  const [period, setPeriod] = useState(currentPeriod());
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const { authFetch } = useAuth();

  const fetchReport = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ propertyId, period });
      const res = await authFetch(`${API_BASE}/budgets/report?${params.toString()}`);
      if (!res.ok) throw new Error("Couldn't load the report.");
      setReport(await res.json());
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [propertyId, period, authFetch]);

  useEffect(() => {
    fetchReport();
  }, [fetchReport]);

  return (
    <div>
      <div className="flex items-center gap-2 mb-3">
        <label htmlFor="report-period" className="text-xs text-slate-500">Month</label>
        <input
          id="report-period"
          type="month"
          value={period}
          onChange={(e) => setPeriod(e.target.value)}
          className="border border-slate-200 rounded-lg px-2 py-1 text-sm"
        />
      </div>

      {loading && <div className="text-sm text-slate-500">Loading...</div>}
      {error && <div className="text-sm text-rose-600 bg-rose-50 border border-rose-200 rounded-lg p-3" role="alert">{error}</div>}

      {!loading && !error && report && report.categories.length === 0 && (
        <EmptyState icon={Wallet} title="Nothing to compare yet" subtitle="Add a budget line and some categorized bank transactions for this month to see a real comparison." />
      )}

      {!loading && !error && report && report.categories.length > 0 && (
        <>
          <div className="bg-white border border-slate-200 rounded-lg p-3 mb-2 flex items-center justify-between text-sm font-semibold">
            <span>Total</span>
            <span>
              ${report.totalBudgeted.toLocaleString()} budgeted · ${report.totalActual.toLocaleString()} actual
            </span>
          </div>
          <div className="space-y-2">
            {report.categories.map((c) => {
              const over = c.variance < 0;
              return (
                <div key={c.category} className="bg-white border border-slate-200 rounded-lg p-3">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium capitalize">{c.category}</span>
                    <span className={`flex items-center gap-1 text-xs font-semibold ${over ? "text-rose-600" : "text-emerald-600"}`}>
                      {over ? <TrendingDown size={13} /> : <TrendingUp size={13} />}
                      {over ? "-" : "+"}${Math.abs(c.variance).toLocaleString()}
                    </span>
                  </div>
                  <p className="text-xs text-slate-500 mt-1">
                    ${c.budgeted.toLocaleString()} budgeted · ${c.actual.toLocaleString()} actual
                  </p>
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
