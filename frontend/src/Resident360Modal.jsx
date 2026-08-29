import { useState, useEffect } from "react";
import { useAuth } from "./AuthContext";
import { X, FileSignature, DollarSign, Wrench, MessageSquare, Phone } from "lucide-react";
import { API_BASE } from "./config";

/**
 * Resident360Modal
 *
 * Priority 31 — pulls together everything already known about one
 * resident (leases, payments, maintenance tickets, communications)
 * into a single view, rather than staff having to check four separate
 * tabs. Purely a read-only aggregation of existing data — no new
 * backend collections, just the new /api/residents/360 endpoint
 * joining across what already exists.
 */

const SECTION_ICONS = { leases: FileSignature, payments: DollarSign, tickets: Wrench, communications: MessageSquare };
const SECTION_LABELS = { leases: "Leases", payments: "Payments", tickets: "Maintenance", communications: "Communications" };

export function LeaseSummary({ lease }) {
  return (
    <div className="border-b border-slate-100 py-2.5 last:border-none text-sm">
      <div className="flex items-center justify-between">
        <span className="font-medium">Unit {lease.unitId}</span>
        <span className="text-xs text-slate-500">{lease.renewalStatus}</span>
      </div>
      <p className="text-xs text-slate-500">
        {new Date(lease.startDate).toLocaleDateString()} – {new Date(lease.endDate).toLocaleDateString()} · ${lease.rent?.toLocaleString()}/mo
      </p>
      {lease.residentPhone && (
        <p className="text-xs text-slate-500 flex items-center gap-1 mt-0.5">
          <Phone size={11} />
          {lease.residentPhone}
        </p>
      )}
    </div>
  );
}

export function PaymentSummary({ payment }) {
  const owed = (payment.amountDue || 0) - (payment.amountPaid || 0);
  return (
    <div className="border-b border-slate-100 py-2 last:border-none text-sm flex items-center justify-between">
      <span>{payment.description || "Charge"}</span>
      <span className={owed > 0 ? "text-amber-600" : "text-emerald-600"}>
        {owed > 0 ? `$${owed.toLocaleString()} due` : "Paid"}
      </span>
    </div>
  );
}

export function TicketSummary({ ticket }) {
  return (
    <div className="border-b border-slate-100 py-2 last:border-none text-sm flex items-center justify-between">
      <span>{ticket.title}</span>
      <span className="text-xs text-slate-500 capitalize">{ticket.status}</span>
    </div>
  );
}

function CommSummary({ comm }) {
  return (
    <div className="border-b border-slate-100 py-2 last:border-none text-sm">
      <span className="text-xs text-slate-400 capitalize">{comm.channel}</span>{" "}
      <span>{comm.subject || comm.body}</span>
    </div>
  );
}

export default function Resident360Modal({ email, name, onClose }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const { authFetch } = useAuth();

  useEffect(() => {
    (async () => {
      try {
        const res = await authFetch(`${API_BASE}/residents/360?email=${encodeURIComponent(email)}`);
        if (!res.ok) throw new Error("Couldn't load this resident's history");
        setData(await res.json());
      } catch (err) {
        setError(err.message);
      }
    })();
  }, [email, authFetch]);

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-30 p-4">
      <div className="bg-white rounded-xl shadow-lg w-full max-w-lg max-h-[85vh] overflow-y-auto p-5">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-semibold">{name || email}'s full history</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600">
            <X size={18} />
          </button>
        </div>

        {error && <p role="alert" className="text-sm text-rose-600">{error}</p>}
        {!data && !error && <div className="h-40 bg-slate-100 rounded-xl animate-pulse" />}

        {data && data.reliability && (
          <div className="flex items-center gap-3 bg-slate-50 border border-slate-200 rounded-xl p-3 mb-4">
            <div
              className={`shrink-0 w-12 h-12 rounded-full flex items-center justify-center text-sm font-bold ${
                data.reliability.score >= 80
                  ? "bg-emerald-100 text-emerald-700"
                  : data.reliability.score >= 60
                  ? "bg-amber-100 text-amber-700"
                  : "bg-rose-100 text-rose-700"
              }`}
              title="A real, transparent formula: on-time payments count fully, late payments count partially, missed payments don't count — not a statistical or ML model."
            >
              {data.reliability.score}
            </div>
            <div>
              <p className="text-sm font-semibold text-slate-700">Payment reliability</p>
              <p className="text-xs text-slate-500">
                {data.reliability.onTimeCount} on-time · {data.reliability.lateCount} late · {data.reliability.missedCount} missed
                {" "}(of {data.reliability.totalCount})
              </p>
            </div>
          </div>
        )}

        {data && (
          <div className="space-y-5">
            {["leases", "payments", "tickets", "communications"].map((section) => {
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
                      {section === "communications" && items.slice(0, 10).map((c) => <CommSummary key={c.id} comm={c} />)}
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
