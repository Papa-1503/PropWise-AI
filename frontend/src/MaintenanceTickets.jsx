import { useState, useEffect, useCallback, useMemo } from "react";
import { useAuth } from "./AuthContext";
import VendorAssignment from "./VendorAssignment";
import EmptyState from "./EmptyState";
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

function GroupedTicketRow({ title, items, selectable, selectedIds, onToggleSelect, onUpdateStatus }) {
  const [expanded, setExpanded] = useState(false);
  const allSelected = items.every((t) => selectedIds.has(t.id));
  const someSelected = items.some((t) => selectedIds.has(t.id));

  function toggleGroupSelect() {
    items.forEach((t) => {
      const isSelected = selectedIds.has(t.id);
      if (allSelected ? isSelected : !isSelected) onToggleSelect(t.id);
    });
  }

  return (
    <div className="border-b border-slate-200 last:border-none py-3 bg-slate-50/60 -mx-2 px-2 rounded-lg">
      <div className="flex items-start gap-4">
        {selectable && (
          <input
            type="checkbox"
            checked={allSelected}
            ref={(el) => el && (el.indeterminate = someSelected && !allSelected)}
            onChange={toggleGroupSelect}
            className="mt-1"
            aria-label={`Select all ${items.length} ${title} tickets`}
          />
        )}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-medium">{title}</span>
            <span className="text-[10px] font-mono bg-violet-50 text-violet-700 rounded-full px-2 py-0.5">
              {items.length} units
            </span>
          </div>
          <button onClick={() => setExpanded((e) => !e)} className="text-[11px] text-indigo-700 hover:underline mt-1">
            {expanded ? "Hide units" : `Show units (${items.map((t) => t.unitId || "—").join(", ")})`}
          </button>
          {expanded && (
            <div className="mt-2 space-y-2 pl-2 border-l-2 border-slate-200">
              {items.map((t) => (
                <TicketRow
                  key={t.id}
                  ticket={t}
                  onUpdateStatus={onUpdateStatus}
                  isStaff={true}
                  selectable={selectable}
                  selected={selectedIds.has(t.id)}
                  onToggleSelect={onToggleSelect}
                />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function TicketRow({ ticket, onUpdateStatus, onVendorAssigned, isStaff, buildingName, selectable, selected, onToggleSelect }) {
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
        {selectable && (
          <input
            type="checkbox"
            checked={selected}
            onChange={() => onToggleSelect(ticket.id)}
            className="mt-1"
            aria-label={`Select ${ticket.title}`}
          />
        )}
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
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [confirmingBulk, setConfirmingBulk] = useState(null); // target status | null
  const [undoState, setUndoState] = useState(null); // { previousStatuses: Map, message } | null
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

  function toggleSelect(ticketId) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(ticketId)) next.delete(ticketId);
      else next.add(ticketId);
      return next;
    });
  }

  // No backend bulk-update endpoint exists — this sends one PATCH per
  // selected ticket. "Undo" is possible because we record each ticket's
  // real previous status before changing it, then can PATCH each one
  // back individually if the person clicks undo.
  function applyBulkStatus(status) {
    const affectedIds = [...selectedIds];
    const previousStatuses = new Map(
      tickets.filter((t) => affectedIds.includes(t.id)).map((t) => [t.id, t.status])
    );

    setTickets((prev) => prev.map((t) => (affectedIds.includes(t.id) ? { ...t, status } : t)));
    setSelectedIds(new Set());
    setConfirmingBulk(null);

    // Set the undo toast immediately, before the network calls, not after
    // awaiting them — real testing (Aug 25, 2026) showed setUndoState was
    // genuinely being called with correct data after the await (confirmed
    // via a diagnostic console.log), but the toast never actually
    // persisted on screen, pointing to something in that async gap. This
    // also gives the person instant feedback rather than waiting on the
    // network for the undo option to appear.
    setUndoState({
      previousStatuses,
      message: `${affectedIds.length} ticket${affectedIds.length !== 1 ? "s" : ""} marked ${STATUS_LABEL[status]}.`,
    });
    setTimeout(() => setUndoState((cur) => (cur?.previousStatuses === previousStatuses ? null : cur)), 8000);

    Promise.all(
      affectedIds.map((id) =>
        authFetch(`${API_BASE}/maintenance/tickets/${id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ status }),
        }).catch(() => null)
      )
    );
  }

  async function handleUndo() {
    if (!undoState) return;
    const { previousStatuses } = undoState;
    setTickets((prev) =>
      prev.map((t) => (previousStatuses.has(t.id) ? { ...t, status: previousStatuses.get(t.id) } : t))
    );
    setUndoState(null);
    await Promise.all(
      [...previousStatuses.entries()].map(([id, status]) =>
        authFetch(`${API_BASE}/maintenance/tickets/${id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ status }),
        }).catch(() => null)
      )
    );
  }

  const filtered = useMemo(
    () => (statusFilter === "all" ? tickets : tickets.filter((t) => t.status === statusFilter)),
    [tickets, statusFilter]
  );

  // Group same-title OPEN tickets together for display (e.g. the same
  // workflow-triggered task landing on several units at once) rather than
  // showing N nearly-identical cards. Only groups status === "open" —
  // resolved/in-progress items always show individually, since grouping
  // there adds no value. A title needs 2+ open tickets to become a group;
  // a single occurrence renders normally via the ungrouped path below.
  const { groups, ungrouped } = useMemo(() => {
    const openByTitle = new Map();
    const ungroupedList = [];
    for (const t of filtered) {
      if (t.status !== "open") {
        ungroupedList.push(t);
        continue;
      }
      if (!openByTitle.has(t.title)) openByTitle.set(t.title, []);
      openByTitle.get(t.title).push(t);
    }
    const groupList = [];
    for (const [title, items] of openByTitle) {
      if (items.length >= 2) groupList.push({ title, items });
      else ungroupedList.push(...items);
    }
    // Preserve original ordering for ungrouped items rather than the
    // Map-insertion order that singling-out would otherwise produce.
    ungroupedList.sort((a, b) => filtered.indexOf(a) - filtered.indexOf(b));
    return { groups: groupList, ungrouped: ungroupedList };
  }, [filtered]);

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

      {isStaff && selectedIds.size > 0 && (
        <div className="flex items-center justify-between bg-slate-900 text-white rounded-lg px-4 py-2.5 mb-3 text-sm">
          <span>{selectedIds.size} selected</span>
          <div className="flex gap-2">
            {["open", "in_progress", "done"].map((s) => (
              <button
                key={s}
                onClick={() => setConfirmingBulk(s)}
                className="text-xs font-semibold bg-white/10 hover:bg-white/20 px-2.5 py-1 rounded"
              >
                Mark {STATUS_LABEL[s]}
              </button>
            ))}
            <button onClick={() => setSelectedIds(new Set())} className="text-xs text-slate-300 hover:text-white px-2">
              Clear
            </button>
          </div>
        </div>
      )}

      {confirmingBulk && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-30 p-4">
          <div className="bg-white rounded-xl shadow-lg w-full max-w-sm p-5">
            <p className="text-sm mb-4">
              Mark <strong>{selectedIds.size}</strong> ticket{selectedIds.size !== 1 ? "s" : ""} as{" "}
              <strong>{STATUS_LABEL[confirmingBulk]}</strong>?
            </p>
            <div className="flex gap-2">
              <button
                onClick={() => applyBulkStatus(confirmingBulk)}
                className="flex-1 text-sm font-semibold bg-slate-900 text-white py-2 rounded-lg"
              >
                Confirm
              </button>
              <button
                onClick={() => setConfirmingBulk(null)}
                className="flex-1 text-sm font-semibold bg-white border border-slate-300 py-2 rounded-lg"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {/* TEMPORARY DIAGNOSTIC — remove once the undo-toast bug is found.
          Not fixed-positioned, so it can't be hidden by any CSS/z-index
          issue — proves whether undoState itself is set, separate from
          whether the actual toast below is visually rendering. */}
      <p className="text-xs bg-yellow-200 text-black p-2 my-2">
        DIAGNOSTIC: undoState is currently {undoState ? `SET ("${undoState.message}")` : "null"}
      </p>

      {undoState && (
        <div className="fixed bottom-4 left-1/2 -translate-x-1/2 bg-slate-900 text-white text-sm px-4 py-2.5 rounded-lg shadow-lg flex items-center gap-3 z-30">
          <span>{undoState.message}</span>
          <button onClick={handleUndo} className="font-semibold underline">Undo</button>
        </div>
      )}

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

      {!loading && !error && (
        <>
          {groups.map((g) => (
            <GroupedTicketRow
              key={g.title}
              title={g.title}
              items={g.items}
              selectable={isStaff}
              selectedIds={selectedIds}
              onToggleSelect={toggleSelect}
              onUpdateStatus={handleUpdateStatus}
            />
          ))}
          {ungrouped.map((ticket) => (
            <TicketRow
              key={ticket.id}
              ticket={ticket}
              onUpdateStatus={handleUpdateStatus}
              onVendorAssigned={handleVendorAssigned}
              isStaff={isStaff}
              buildingName={isStaff ? getPropertyName(ticket.propertyId) : null}
              selectable={isStaff}
              selected={selectedIds.has(ticket.id)}
              onToggleSelect={toggleSelect}
            />
          ))}
        </>
      )}
    </div>
  );
}
