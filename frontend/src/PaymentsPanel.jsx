import { useState, useEffect, useCallback } from "react";
import { useAuth } from "./AuthContext";
import { API_BASE } from "./config";
import EmptyState from "./EmptyState";
import { DollarSign } from "lucide-react";
import AutopaySetup from "./AutopaySetup";


const STATUS_STYLE = {
  paid: "bg-emerald-50 text-emerald-700 border-emerald-200",
  pending: "bg-slate-50 text-slate-600 border-slate-200",
  late: "bg-rose-50 text-rose-700 border-rose-200",
};

function RecordPaymentForm({ charge, onRecorded, authFetch }) {
  const [amount, setAmount] = useState("");
  const [method, setMethod] = useState("ach");
  const [saving, setSaving] = useState(false);

  async function submit() {
    if (!amount || Number(amount) <= 0) return;
    setSaving(true);
    try {
      const res = await authFetch(`${API_BASE}/payments/${charge.id}/record`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ amountPaid: Number(amount), method }),
      });
      if (res.ok) {
        onRecorded(await res.json());
        setAmount("");
      }
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="flex items-center gap-1.5 mt-1.5">
      <input
        type="number"
        placeholder="Amount"
        value={amount}
        onChange={(e) => setAmount(e.target.value)}
        className="w-20 text-xs border border-slate-200 rounded px-1.5 py-1"
      />
      <select
        value={method}
        onChange={(e) => setMethod(e.target.value)}
        className="text-xs border border-slate-200 rounded px-1 py-1"
      >
        <option value="ach">ACH</option>
        <option value="card">Card</option>
        <option value="check">Check</option>
        <option value="cash">Cash</option>
        <option value="other">Other</option>
      </select>
      <button
        onClick={submit}
        disabled={saving}
        className="text-xs font-semibold bg-slate-900 disabled:bg-slate-300 text-white px-2.5 py-1 rounded"
      >
        {saving ? "…" : "Record"}
      </button>
    </div>
  );
}

export default function PaymentsPanel({ propertyId }) {
  const [charges, setCharges] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("all");
  const { authFetch, user, getPropertyName } = useAuth();
  const isStaff = user?.role === "staff";

  const fetchCharges = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (propertyId) params.set("propertyId", propertyId);
      const res = await authFetch(`${API_BASE}/payments?${params.toString()}`);
      if (res.ok) {
        const data = await res.json();
        setCharges(data.charges || []);
      }
    } finally {
      setLoading(false);
    }
  }, [propertyId, authFetch]);

  useEffect(() => {
    fetchCharges();
  }, [fetchCharges]);

  function handleRecorded(updated) {
    setCharges((prev) => prev.map((c) => (c.id === updated.id ? updated : c)));
  }

  const filtered = filter === "all" ? charges : charges.filter((c) => c.status === filter);
  const totalOutstanding = charges
    .filter((c) => c.status !== "paid")
    .reduce((sum, c) => sum + (c.amountDue - c.amountPaid), 0);

  if (loading) return <div className="h-40 bg-slate-100 rounded-xl animate-pulse" />;

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5">
      <div className="flex items-center justify-between mb-1">
        <h2 className="text-lg font-semibold">Payments</h2>
        <span className="text-xs text-slate-500">${totalOutstanding.toLocaleString()} outstanding</span>
      </div>

      {!isStaff && (
        <div className="my-3">
          <AutopaySetup />
        </div>
      )}

      <div className="flex gap-1 mb-3">
        {["all", "pending", "late", "paid"].map((s) => (
          <button
            key={s}
            onClick={() => setFilter(s)}
            className={`text-[11px] px-2.5 py-1 rounded-full border capitalize ${
              filter === s ? "bg-slate-900 text-white border-slate-900" : "border-slate-200 text-slate-500"
            }`}
          >
            {s}
          </button>
        ))}
      </div>

     {filtered.length === 0 ? (
        <EmptyState
          icon={DollarSign}
          title="No charges match this filter"
          subtitle="Charges will show up here once rent or fees are recorded for this filter."
        />
      ) : (
        <div className="space-y-2">
          {filtered.map((c) => (
            <div key={c.id} className="border border-slate-100 rounded-lg px-3 py-2.5">
              <div className="flex items-center justify-between">
                <div>
                  {isStaff && getPropertyName(c.propertyId) && (
                    <span className="text-xs text-slate-500 block">{getPropertyName(c.propertyId)}</span>
                  )}
                  <span className="text-sm font-medium">Unit {c.unitId}</span>
                  <span className="text-xs text-slate-500 ml-2">{c.description}</span>
                </div>
                <span className={`text-[10px] font-mono uppercase px-2 py-0.5 rounded-full border ${STATUS_STYLE[c.status]}`}>
                  {c.status}
                </span>
              </div>
              <div className="text-xs text-slate-500 mt-1">
                ${c.amountDue.toFixed(2)} due {new Date(c.dueDate).toLocaleDateString()}
                {c.amountPaid > 0 && ` — $${c.amountPaid.toFixed(2)} paid`}
              </div>
              {isStaff && c.status !== "paid" && (
                <RecordPaymentForm charge={c} onRecorded={handleRecorded} authFetch={authFetch} />
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
