import { useState, useEffect, useCallback } from "react";
import { useAuth } from "./AuthContext";
import EmptyState from "./EmptyState";
import { UserPlus2, Phone, Mail } from "lucide-react";
import { API_BASE } from "./config";

/**
 * LeadsList
 *
 * Found via a second external audit (Priority 43): the backend
 * (routers/leads.py) has real, working, staff-gated endpoints —
 * GET /api/leads (list) and PATCH /api/leads/:id/status — but the only
 * existing frontend usage was LeadCaptureForm.jsx, which just submits
 * new leads via the public /apply page. No staff-facing view existed
 * to browse leads or move them through the funnel. Seventh instance of
 * the same "backend exists, no frontend" pattern found today.
 *
 * Note: list_leads returns the id field as `_id` (string), not `id`
 * like the Leases/Screening endpoints — confirmed by reading the
 * backend directly before assuming either way.
 */

const STATUS_STYLE = {
  new: "bg-slate-50 text-slate-500 border-slate-200",
  toured: "bg-indigo-50 text-indigo-700 border-indigo-200",
  applied: "bg-amber-50 text-amber-700 border-amber-200",
  signed: "bg-emerald-50 text-emerald-700 border-emerald-200",
  declined: "bg-rose-50 text-rose-700 border-rose-200",
};
const STATUS_LABEL = {
  new: "New",
  toured: "Toured",
  applied: "Applied",
  signed: "Signed",
  declined: "Declined",
};

function LeadRow({ lead, buildingName, onStatusChange }) {
  return (
    <div className="border-b border-slate-100 py-3 last:border-none">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium">{lead.name}</span>
        <select
          value={lead.status}
          onChange={(e) => onStatusChange(lead._id, e.target.value)}
          className={`text-[11px] font-mono uppercase px-2 py-0.5 rounded-full border ${STATUS_STYLE[lead.status]}`}
        >
          {Object.entries(STATUS_LABEL).map(([val, label]) => (
            <option key={val} value={val}>{label}</option>
          ))}
        </select>
      </div>
      <div className="flex items-center gap-3 text-xs text-slate-500 mt-1">
        <span className="flex items-center gap-1">
          <Mail size={11} />
          {lead.email}
        </span>
        {lead.phone && (
          <span className="flex items-center gap-1">
            <Phone size={11} />
            {lead.phone}
          </span>
        )}
      </div>
      {lead.message && <p className="text-xs text-slate-600 mt-1 italic">"{lead.message}"</p>}
      <p className="text-[11px] text-slate-400 mt-1">
        {buildingName ? <span>{buildingName} · </span> : !lead.propertyId && <span>General inquiry · </span>}
        {lead.unitId && <span>Unit {lead.unitId} · </span>}
        {lead.createdAt ? new Date(lead.createdAt).toLocaleDateString() : ""}
      </p>
    </div>
  );
}

export default function LeadsList({ propertyId }) {
  const [leads, setLeads] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const { authFetch, getPropertyName } = useAuth();

  const fetchLeads = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (propertyId) params.set("propertyId", propertyId);
      const res = await authFetch(`${API_BASE}/leads?${params.toString()}`);
      if (res.ok) {
        const data = await res.json();
        setLeads(data.leads || []);
      } else {
        setError(res.status === 403 ? "You don't have access to this." : "Couldn't load leads — try again.");
      }
    } catch {
      setError("Couldn't load leads — check your connection and try again.");
    } finally {
      setLoading(false);
    }
  }, [propertyId, authFetch]);

  useEffect(() => {
    fetchLeads();
  }, [fetchLeads]);

  async function handleStatusChange(leadId, status) {
    setLeads((prev) => prev.map((l) => (l._id === leadId ? { ...l, status } : l)));
    try {
      await authFetch(`${API_BASE}/leads/${leadId}/status`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status }),
      });
    } catch {
      fetchLeads();
    }
  }

  return (
    <div className="max-w-2xl mx-auto">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-lg font-semibold">Leads</h2>
      </div>

      <p className="text-xs text-slate-500 bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 mb-3">
        Leads come in through the public application form — track them here from first inquiry through a signed lease.
      </p>

      {loading ? (
        <div className="h-40 bg-slate-100 rounded-xl animate-pulse" />
      ) : error ? (
        <p role="alert" aria-live="polite" className="text-sm text-rose-600 bg-rose-50 border border-rose-200 rounded-xl px-4 py-3">{error}</p>
      ) : leads.length === 0 ? (
        <EmptyState
          icon={UserPlus2}
          title="No leads yet"
          subtitle="Prospective tenants who apply through the public form will show up here."
        />
      ) : (
        <div className="bg-white border border-slate-200 rounded-xl px-4">
          {leads.map((l) => (
            <LeadRow
              key={l._id}
              lead={l}
              buildingName={!propertyId ? getPropertyName(l.propertyId) : null}
              onStatusChange={handleStatusChange}
            />
          ))}
        </div>
      )}
    </div>
  );
}
