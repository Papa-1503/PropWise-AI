import { useState, useEffect } from "react";
import { useAuth } from "./AuthContext";
import { X, FileSignature, DollarSign, Wrench, ClipboardCheck } from "lucide-react";
import { API_BASE } from "./config";
import { LeaseSummary, PaymentSummary, TicketSummary } from "./Resident360Modal";

/**
 * UnitHistoryModal
 *
 * Fallback view for units that don't currently have a resident email
 * on file — vacant units, or occupied ones where the lease was created
 * without an email. Resident360Modal requires an email to look someone
 * up; this modal instead queries by propertyId+unitId directly via the
 * existing GET /api/units/360 endpoint, so a unit number is always
 * clickable and always opens *something* useful, regardless of
 * whether a resident record is linked.
 *
 * Reuses LeaseSummary/PaymentSummary/TicketSummary from
 * Resident360Modal.jsx rather than duplicating them — same row
 * rendering either way, just a different query shape and an added
 * Inspections section (unit_360 returns inspections; resident_360
 * doesn't, since inspections are tied to a unit, not a person).
 */

const SECTION_ICONS = { leases: FileSignature, payments: DollarSign, tickets: Wrench, inspections: ClipboardCheck };
const SECTION_LABELS = { leases: "Leases", payments: "Payments", tickets: "Maintenance", inspections: "Inspections" };

const INSPECTION_TYPE_LABEL = {
  "move-in": "Move-in",
  "move-out": "Move-out",
  annual: "Annual",
  turnover: "Turnover",
};

function InspectionSummary({ inspection }) {
  const items = inspection.items || [];
  const flagged = items.filter((i) => i.status === "flag" || i.status === "fail");
  return (
    <div className="border-b border-slate-100 py-2.5 last:border-none text-sm">
      <div className="flex items-center justify-between">
        <span className="font-medium">{INSPECTION_TYPE_LABEL[inspection.type] || inspection.type}</span>
        <span className={flagged.length > 0 ? "text-xs text-rose-600" : "text-xs text-emerald-600"}>
          {flagged.length > 0 ? `${flagged.length} flagged` : "Clean"}
        </span>
      </div>
      <p className="text-xs text-slate-500">
        {inspection.inspectorName && <span>{inspection.inspectorName} · </span>}
        {inspection.createdAt ? new Date(inspection.createdAt).toLocaleDateString() : ""}
      </p>
    </div>
  );
}

export default function UnitHistoryModal({ propertyId, unitId, onClose }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const { authFetch } = useAuth();

  useEffect(() => {
    (async () => {
      try {
        const params = new URLSearchParams({ propertyId, unitId });
        const res = await authFetch(`${API_BASE}/units/360?${params.toString()}`);
        if (!res.ok) throw new Error("Couldn't load this unit's history");
        setData(await res.json());
      } catch (err) {
        setError(err.message);
      }
    })();
  }, [propertyId, unitId, authFetch]);

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-30 p-4">
      <div className="bg-white rounded-xl shadow-lg w-full max-w-lg max-h-[85vh] overflow-y-auto p-5">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-semibold">Unit {unitId} history</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600">
            <X size={18} />
          </button>
        </div>

        {error && <p role="alert" className="text-sm text-rose-600">{error}</p>}
        {!data && !error && <div className="h-40 bg-slate-100 rounded-xl animate-pulse" />}

        {data && (
          <div className="space-y-5">
            {["leases", "payments", "tickets", "inspections"].map((section) => {
              const Icon = SECTION_ICONS[section];
              const items = data[section] || [];
              return (
                <div key={section}>
                  <h4 className="text-xs font-semibold uppercase text-slate-400 flex items-center gap-1.5 mb-1.5">
                    <Icon size={12} />
                    {SECTION_LABELS[section]} ({items.length})
                  </h4>
                  {items.length === 0 ? (
                    <p className="text-xs text-slate-400">Nothing here yet.</p>
                  ) : (
                    <div>
                      {section === "leases" && items.map((l) => <LeaseSummary key={l.id} lease={l} />)}
                      {section === "payments" && items.slice(0, 10).map((p) => <PaymentSummary key={p.id} payment={p} />)}
                      {section === "tickets" && items.slice(0, 10).map((t) => <TicketSummary key={t.id} ticket={t} />)}
                      {section === "inspections" && items.slice(0, 10).map((i) => <InspectionSummary key={i.id} inspection={i} />)}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
