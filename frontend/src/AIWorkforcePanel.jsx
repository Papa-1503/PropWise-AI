import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { ChevronDown, ChevronUp } from "lucide-react";
import { useAuth } from "./AuthContext";
import { API_BASE } from "./config";


function StatLine({ label, value, to }) {
  const navigate = useNavigate();
  const isClickable = Boolean(to) && value !== null && value !== undefined;

  const content = (
    <>
      <span className={isClickable ? "text-indigo-700 group-hover:underline" : "text-slate-500"}>{label}</span>
      <span className="font-semibold">
        {value === null || value === undefined ? (
          <span className="text-slate-300 font-normal italic">not tracked</span>
        ) : typeof value === "number" && label.toLowerCase().includes("revenue") ? (
          `$${value.toLocaleString()}`
        ) : (
          value
        )}
      </span>
    </>
  );

  if (isClickable) {
    return (
      <button
        onClick={() => navigate(to)}
        className="w-full flex justify-between text-xs py-1 group hover:bg-indigo-50/60 -mx-1 px-1 rounded"
      >
        {content}
      </button>
    );
  }
  return <div className="flex justify-between text-xs py-1">{content}</div>;
}

/**
 * DrillDownStatLine
 *
 * Added in direct response to a real product review concern: a
 * headline AI-attributed dollar figure ("$160,880 revenue protected")
 * invites a reasonable "how was this calculated?" from a
 * sophisticated operator. Rather than navigating away like StatLine's
 * `to` prop does, this expands IN PLACE to show the real, itemized
 * records that sum to the total - the honest, verifiable answer,
 * always backed by GET /api/dashboard/workforce's own real breakdown
 * arrays (routers/dashboard.py), never a client-side estimate.
 */
function DrillDownStatLine({ label, value, breakdown, renderItem, emptyText }) {
  const [expanded, setExpanded] = useState(false);
  const hasItems = Array.isArray(breakdown) && breakdown.length > 0;

  return (
    <div className="text-xs">
      <button
        onClick={() => setExpanded((v) => !v)}
        disabled={!hasItems}
        className="w-full flex justify-between items-center py-1 group hover:bg-indigo-50/60 -mx-1 px-1 rounded disabled:cursor-default"
      >
        <span className={hasItems ? "text-indigo-700 group-hover:underline flex items-center gap-1" : "text-slate-500"}>
          {label}
          {hasItems && (expanded ? <ChevronUp size={11} /> : <ChevronDown size={11} />)}
        </span>
        <span className="font-semibold">
          {value === null || value === undefined ? (
            <span className="text-slate-300 font-normal italic">not tracked</span>
          ) : (
            `$${value.toLocaleString()}`
          )}
        </span>
      </button>
      {expanded && (
        <div className="mt-1 mb-1.5 ml-1 pl-2 border-l-2 border-indigo-100 space-y-1">
          {hasItems ? breakdown.map(renderItem) : (
            <p className="text-[10px] text-slate-400 italic py-1">{emptyText}</p>
          )}
        </div>
      )}
    </div>
  );
}

function AgentCard({ name, displayName, tracked, note, children }) {
  return (
    <div className={`rounded-lg border p-3.5 ${tracked ? "border-slate-200 bg-white" : "border-dashed border-slate-200 bg-slate-50"}`}>
      <div className="flex items-center justify-between mb-1.5">
        <h4 className="text-sm font-semibold">
          {displayName ? (
            <>
              {displayName} <span className="text-slate-400 font-normal">· {name}</span>
            </>
          ) : (
            name
          )}
        </h4>
        {!tracked && (
          <span className="text-[9px] font-mono uppercase text-slate-400 bg-slate-100 px-1.5 py-0.5 rounded">
            not connected
          </span>
        )}
      </div>
      {children}
      {!tracked && note && <p className="text-[10px] text-slate-400 italic mt-1.5">{note}</p>}
    </div>
  );
}

export default function AIWorkforcePanel({ propertyId }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const { authFetch } = useAuth();

  const fetchWorkforce = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (propertyId) params.set("propertyId", propertyId);
      const res = await authFetch(`${API_BASE}/dashboard/workforce?${params.toString()}`);
      if (res.ok) setData(await res.json());
    } finally {
      setLoading(false);
    }
  }, [propertyId, authFetch]);

  useEffect(() => {
    fetchWorkforce();
  }, [fetchWorkforce]);

  if (loading) return <div className="h-48 bg-slate-100 rounded-xl animate-pulse" />;
  if (!data) return null;

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5">
      <h2 className="text-lg font-semibold mb-1">AI Workforce</h2>
      <p className="text-xs text-slate-500 mb-4">Last {data.windowDays} days</p>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <AgentCard name="LeasingAI" displayName={data.leasingAI.displayName} tracked={data.leasingAI.tracked} note={data.leasingAI.note}>
          <StatLine label="Leads Processed" value={data.leasingAI.leadsProcessed} to="/app/leads" />
          {/* No dedicated Tours page exists in the frontend yet (tours.py backend
              only) — routes to Leads as the closest real destination, since every
              booked tour already creates/links a lead record there. */}
          <StatLine label="Tours Scheduled" value={data.leasingAI.toursScheduled} to="/app/leads" />
          <StatLine label="Applications" value={data.leasingAI.applications} to="/app/screening" />
          <StatLine label="Leases Signed" value={data.leasingAI.leasesSigned} to="/app/leases" />
        </AgentCard>

        <AgentCard name="OperationsAI" displayName={data.operationsAI.displayName} tracked={data.operationsAI.tracked}>
          <StatLine label="Actions Suggested" value={data.operationsAI.actionsSuggested} to="/app/actions" />
          <StatLine label="Actions Approved" value={data.operationsAI.actionsApproved} to="/app/actions" />
          <DrillDownStatLine
            label="Est. Revenue Protected"
            value={data.operationsAI.revenueProtected}
            breakdown={data.operationsAI.revenueProtectedBreakdown}
            emptyText="No completed actions with an estimated value in this window."
            renderItem={(item, i) => (
              <div key={i} className="flex justify-between gap-2 py-0.5">
                <span className="text-slate-600 truncate">{item.title}</span>
                <span className="text-slate-500 shrink-0">${item.estimatedValue.toLocaleString()}</span>
              </div>
            )}
          />
          <p className="text-[10px] text-slate-400 italic mt-1">
            AI-estimated impact of completed actions — not an independently verified figure.
          </p>
        </AgentCard>

        <AgentCard name="CollectionsAI" displayName={data.collectionsAI.displayName} tracked={data.collectionsAI.tracked} note={data.collectionsAI.note}>
          <StatLine label="Residents Contacted" value={data.collectionsAI.residentsContacted} to="/app/communications" />
          <DrillDownStatLine
            label="Recovered Revenue"
            value={data.collectionsAI.recoveredRevenue}
            breakdown={data.collectionsAI.recoveredRevenueBreakdown}
            emptyText="No payments recovered after their due date in this window."
            renderItem={(item, i) => (
              <div key={i} className="flex justify-between gap-2 py-0.5">
                <span className="text-slate-600">Unit {item.unitId} · {item.daysLate}d late</span>
                <span className="text-slate-500 shrink-0">${item.amountPaid.toLocaleString()}</span>
              </div>
            )}
          />
          <p className="text-[10px] text-slate-400 italic mt-1">
            Real, verified — sum of actual payments received after their due date.
          </p>
        </AgentCard>

        <AgentCard name="MaintenanceAI" displayName={data.maintenanceAI.displayName} tracked={data.maintenanceAI.tracked}>
          <StatLine label="Tickets Created" value={data.maintenanceAI.ticketsCreated} to="/app/maintenance" />
          <StatLine label="Auto-created from Inspections" value={data.maintenanceAI.autoCreatedFromInspections} to="/app/inspections" />
          <StatLine label="Failures Prevented" value={data.maintenanceAI.failuresPrevented} />
        </AgentCard>
      </div>
    </div>
  );
}
