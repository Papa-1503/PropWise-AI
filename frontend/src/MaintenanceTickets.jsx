import { useState, useEffect, useCallback, useMemo } from "react";
import { useAuth } from "./AuthContext";
import VendorAssignment from "./VendorAssignment";import EmptyState from "./EmptyState";
import { Wrench } from "lucide-react";

/**
 * MaintenanceTickets
 *
 * Live ticket list wired to a real backend — no hardcoded data.
 *
 * Assumptions (adjust to match your actual backend):
 *   GET  /api/maintenance/tickets?propertyId=&status=   -> list tickets
 *   PATCH /api/maintenance/tickets/:id                  -> update status/assignee
 *
 * Expected ticket shape from the API:
 * {
 *   id, title, unitId, propertyId, status: "open"|"in_progress"|"done",
 *   priority: "normal"|"urgent", source: "resident"|"inspection",
 *   sourceInspectionId, assignee, category, createdAt,
 *   assignedVendorName, estimatedCost, estimatedArrivalHours
 * }
 */

import { API_BASE } from "./config";

const STATUS_LABEL = { open: "Open", in_progress: "In progress", done: "Resolved" };
const STATUS_STYLE = {
  open: "bg-amber-50 text-amber-700 border-amber-200",
  in_progress: "bg-blue-50 text-blue-700 border-blue-200",
  done: "bg-emerald-50 text-emerald-700 border-emerald-200",
};

function TicketRow({ ticket, onUpdateStatus, onVendorAssigned, isStaff, buildingName }) {
  const [updating, setUpdating] = useState(false);
  const [showVendorPanel, setShowVendorPanel] = useState(false);

  const cycleStatus = async () => {
    const order = ["open", "in_progress", "done"];
    const next = order[(order.indexOf(ticket.status) + 1) % order.length];
    setUpdating(true);
    await onUpdateStatus(ticket.id, next);
    setUpdating(false);
  };

  return (
    <div className="border-b border-slate-200 last:border-none py-3">
      <div className="flex items-start gap-4">
        {isStaff && (
          <span className="font-mono text-xs text-slate-400 pt-0.5" title={ticket.id}>
            #{ticket.id.slice(-6)}
          </span>
        )}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-medium">{ticket.title}</span>
            {ticket.source === "inspection" && (
              <span className="text-[10px] font-mono bg-indigo-50 text-indigo-700 rounded-full px-2 py-0.5">
                auto-created
              </span>
            )}
            {ticket.priority === "urgent" && (
              <span className="text-[10px] font-mono bg-rose-50 text-rose-700 rounded-full px-2 py-0.5">
                urgent
              </span>
            )}
          </div>
          <p className="text-xs text-slate-500 mt-0.5">
            {buildingName && <span className="font-medium text-slate-600">{buildingName}</span>}
            {buildingName && " · "}
            Unit {ticket.unitId} · {ticket.assignee || "Unassigned"} ·{" "}
            {ticket.createdAt ? new Date(ticket.createdAt).toLocaleDateString() : ""}
          </p>
          {ticket.assignedVendorName && (
            <p className="text-xs text-emerald-700 mt-1">
              ✓ Assigned to {ticket.assignedVendorName}
              {ticket.estimatedArrivalHours != null && ` · ~${ticket.estimatedArrivalHours}h arrival`}
              {ticket.estimatedCost != null && ` · $${ticket.estimatedCost}`}
            </p>
          )}
          {isStaff && ticket.status !== "done" && (
            <button
              onClick={() => setShowVendorPanel((s) => !s)}
              className="text-[11px] text-slate-500 underline mt-1"
            >
              {showVendorPanel ? "Hide vendors" : ticket.assignedVendorName ? "Reassign vendor" : "Assign vendor"}
            </button>
          )}
        </div>
        <button
          onClick={cycleStatus}
          disabled={updating}
          className={`text-[11px] font-mono uppercase px-2.5 py-1 rounded-full border whitespace-nowrap ${STATUS_STYLE[ticket.status]}`}
          title="Click to advance status"
        >
          {updating ? "..." : STATUS_LABEL[ticket.status]}
        </button>
      </div>

      {showVendorPanel && (
        <div className="mt-2 ml-[68px]">
          <VendorAssignment
            ticketId={ticket.id}
            category={ticket.category}
            onAssigned={(updated) => {
              onVendorAssigned(updated);
              setShowVendorPanel(false);
            }}
          />
        </div>
      )}
    </div>
  );
}

export default function MaintenanceTickets({ propertyId }) {
  const [tickets, setTickets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [statusFilter, setStatusFilter] = useState("all");
  const [refreshKey, setRefreshKey] = useState(0);
  const { authFetch, user, getPropertyName } = useAuth();
  const isStaff = user?.role === "staff";

  function handleVendorAssigned(updatedTicket) {
    setTickets((prev) => prev.map((t) => (t.id === updatedTicket.id ? updatedTicket : t)));
  }

  const fetchTickets = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (propertyId) params.set("propertyId", propertyId);
      const res = await authFetch(`${API_BASE}/maintenance/tickets?${params.toString()}`);
      if (!res.ok) throw new Error(`Server returned ${res.status}`);
      const data = await res.json();
      setTickets(data.tickets || data); // tolerate either { tickets: [...] } or a bare array
    } catch (err) {
      setError(err.message || "Couldn't load maintenance tickets.");
    } finally {
      setLoading(false);
    }
  }, [propertyId, authFetch]);

  useEffect(() => {
    fetchTickets();
  }, [fetchTickets, refreshKey]);

  const handleUpdateStatus = async (ticketId, status) => {
    // optimistic update
    setTickets((prev) => prev.map((t) => (t.id === ticketId ? { ...t, status } : t)));
    try {
      const res = await authFetch(`${API_BASE}/maintenance/tickets/${ticketId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status }),
      });
      if (!res.ok) throw new Error("Update failed");
    } catch {
      // roll back on failure
      fetchTickets();
    }
  };

  const filtered = useMemo(
    () => (statusFilter === "all" ? tickets : tickets.filter((t) => t.status === statusFilter)),
    [tickets, statusFilter]
  );

  const urgentOpenCount = tickets.filter((t) => t.status !== "done" && t.priority === "urgent").length;

  return (
    <div className="max-w-2xl mx-auto p-5 bg-white rounded-xl border border-slate-200">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-lg font-semibold">Maintenance</h2>
          {urgentOpenCount > 0 && (
            <p className="text-xs text-rose-600 mt-0.5">{urgentOpenCount} urgent ticket{urgentOpenCount !== 1 ? "s" : ""} open</p>
          )}
        </div>
        <div className="flex gap-1">
          {["all", "open", "in_progress", "done"].map((s) => (
            <button
              key={s}
              onClick={() => setStatusFilter(s)}
              className={`text-[11px] px-2.5 py-1 rounded-full border ${
                statusFilter === s ? "bg-slate-900 text-white border-slate-900" : "border-slate-200 text-slate-500"
              }`}
            >
              {s === "all" ? "All" : STATUS_LABEL[s]}
            </button>
          ))}
        </div>
      </div>

      {loading && <p className="text-sm text-slate-400">Loading tickets…</p>}

      {error && (
        <div className="text-sm text-rose-600 bg-rose-50 border border-rose-200 rounded px-3 py-2 flex items-center justify-between">
          <span>{error}</span>
          <button onClick={() => setRefreshKey((k) => k + 1)} className="underline text-xs">
            Retry
          </button>
        </div>
      )}

     {!loading && !error && filtered.length === 0 && (
        <EmptyState
          icon={Wrench}
          title="No tickets match this filter"
          subtitle="Try a different status, or check back once new maintenance requests come in."
        />
      )}

      {!loading &&
        !error &&
        filtered.map((ticket) => (
          <TicketRow
            key={ticket.id}
            ticket={ticket}
            onUpdateStatus={handleUpdateStatus}
            onVendorAssigned={handleVendorAssigned}
            isStaff={isStaff}
            buildingName={isStaff ? getPropertyName(ticket.propertyId) : null}
          />
        ))}
    </div>
  );
}
