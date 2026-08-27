import { useState, useEffect, useCallback } from "react";
import { useAuth } from "./AuthContext";
import { API_BASE } from "./config";


function StatLine({ label, value }) {
  return (
    <div className="flex justify-between text-xs py-1">
      <span className="text-slate-500">{label}</span>
      <span className="font-semibold">
        {value === null || value === undefined ? (
          <span className="text-slate-300 font-normal italic">not tracked</span>
        ) : typeof value === "number" && label.toLowerCase().includes("revenue") ? (
          `$${value.toLocaleString()}`
        ) : (
          value
        )}
      </span>
    </div>
  );
}

function AgentCard({ name, tracked, note, children }) {
  return (
    <div className={`rounded-lg border p-3.5 ${tracked ? "border-slate-200 bg-white" : "border-dashed border-slate-200 bg-slate-50"}`}>
      <div className="flex items-center justify-between mb-1.5">
        <h4 className="text-sm font-semibold">{name}</h4>
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
        <AgentCard name="LeasingAI" tracked={data.leasingAI.tracked} note={data.leasingAI.note}>
          <StatLine label="Leads Processed" value={data.leasingAI.leadsProcessed} />
          <StatLine label="Tours Scheduled" value={data.leasingAI.toursScheduled} />
          <StatLine label="Applications" value={data.leasingAI.applications} />
          <StatLine label="Leases Signed" value={data.leasingAI.leasesSigned} />
        </AgentCard>

        <AgentCard name="OperationsAI" tracked={data.operationsAI.tracked}>
          <StatLine label="Actions Suggested" value={data.operationsAI.actionsSuggested} />
          <StatLine label="Actions Approved" value={data.operationsAI.actionsApproved} />
          <StatLine label="Est. Revenue Protected" value={data.operationsAI.revenueProtected} />
          <p className="text-[10px] text-slate-400 italic mt-1">
            AI-estimated impact of completed actions — not an independently verified figure.
          </p>
        </AgentCard>

        <AgentCard name="CollectionsAI" tracked={data.collectionsAI.tracked} note={data.collectionsAI.note}>
          <StatLine label="Residents Contacted" value={data.collectionsAI.residentsContacted} />
          <StatLine label="Recovered Revenue" value={data.collectionsAI.recoveredRevenue} />
          <p className="text-[10px] text-slate-400 italic mt-1">
            Real, verified — sum of actual payments received after their due date.
          </p>
        </AgentCard>

        <AgentCard name="MaintenanceAI" tracked={data.maintenanceAI.tracked}>
          <StatLine label="Tickets Created" value={data.maintenanceAI.ticketsCreated} />
          <StatLine label="Auto-created from Inspections" value={data.maintenanceAI.autoCreatedFromInspections} />
          <StatLine label="Failures Prevented" value={data.maintenanceAI.failuresPrevented} />
        </AgentCard>
      </div>
    </div>
  );
}
