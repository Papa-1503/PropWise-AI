import { useState, useEffect, useCallback } from "react";
import { useAuth } from "./AuthContext";
import { API_BASE } from "./config";


/**
 * VendorAssignment
 *
 * Lets staff pick a vendor for a specific ticket. Distance/arrival-hours
 * are manually maintained fields on each vendor record (see backend
 * models.py note) — not a live ETA calculation.
 */
export default function VendorAssignment({ ticketId, category, onAssigned }) {
  const [vendors, setVendors] = useState([]);
  const [loading, setLoading] = useState(true);
  const [assigningId, setAssigningId] = useState(null);
  const [sortBy, setSortBy] = useState("rating");
  const { authFetch } = useAuth();

  const fetchVendors = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (category) params.set("category", category);
      const res = await authFetch(`${API_BASE}/vendors?${params.toString()}`);
      if (res.ok) {
        const data = await res.json();
        setVendors(data.vendors || []);
      }
    } finally {
      setLoading(false);
    }
  }, [category, authFetch]);

  useEffect(() => {
    fetchVendors();
  }, [fetchVendors]);

  const sorted = [...vendors].sort((a, b) => {
    if (sortBy === "rating") return (b.rating || 0) - (a.rating || 0);
    if (sortBy === "distance") return (a.distanceMiles ?? 999) - (b.distanceMiles ?? 999);
    if (sortBy === "cost") return (a.baseCost ?? 999999) - (b.baseCost ?? 999999);
    if (sortBy === "arrival") return (a.avgArrivalHours ?? 999) - (b.avgArrivalHours ?? 999);
    return 0;
  });

  async function handleAssign(vendor) {
    setAssigningId(vendor.id);
    try {
      const res = await authFetch(`${API_BASE}/maintenance/tickets/${ticketId}/assign-vendor`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ vendorId: vendor.id }),
      });
      if (res.ok) {
        const updated = await res.json();
        onAssigned?.(updated);
      }
    } finally {
      setAssigningId(null);
    }
  }

  if (loading) return <p className="text-xs text-slate-400">Loading vendors…</p>;
  if (vendors.length === 0) return <p className="text-xs text-slate-400">No vendors available for this category yet.</p>;

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold">Assign vendor</h3>
        <select
          value={sortBy}
          onChange={(e) => setSortBy(e.target.value)}
          className="text-xs border border-slate-200 rounded px-2 py-1"
        >
          <option value="rating">Sort: Rating</option>
          <option value="distance">Sort: Distance</option>
          <option value="cost">Sort: Cost</option>
          <option value="arrival">Sort: Arrival time</option>
        </select>
      </div>

      <div className="space-y-2">
        {sorted.map((v) => (
          <div key={v.id} className="flex items-center justify-between border border-slate-100 rounded-lg px-3 py-2">
            <div>
              <div className="text-sm font-medium">{v.name}</div>
              <div className="text-[11px] text-slate-500 flex gap-3 mt-0.5">
                <span>★ {v.rating}</span>
                {v.distanceMiles != null && <span>{v.distanceMiles} mi</span>}
                {v.avgArrivalHours != null && <span>~{v.avgArrivalHours}h arrival</span>}
                {v.baseCost != null && <span>${v.baseCost}</span>}
              </div>
            </div>
            <button
              onClick={() => handleAssign(v)}
              disabled={assigningId === v.id}
              className="text-xs font-semibold bg-slate-900 disabled:bg-slate-300 text-white px-3 py-1.5 rounded-lg"
            >
              {assigningId === v.id ? "Assigning…" : "Assign"}
            </button>
          </div>
        ))}
      </div>
      <p className="text-[10px] text-slate-400 italic mt-2">
        Distance and arrival time are estimates maintained on each vendor's profile, not a live calculation.
      </p>
    </div>
  );
}
