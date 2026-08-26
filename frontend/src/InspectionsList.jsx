import { useState, useEffect, useCallback } from "react";
import { useAuth } from "./AuthContext";
import InspectionChecklist from "./InspectionChecklist";
import EmptyState from "./EmptyState";
import { ClipboardCheck, Plus } from "lucide-react";
import { API_BASE } from "./config";

/**
 * InspectionsList
 *
 * This is the piece that was missing entirely: a way to see and open
 * already-created inspection records (like an auto-generated turnover
 * checklist), rather than the app only ever offering a blank "start a
 * new inspection" form. Handles list <-> detail switching internally.
 */

const STATUS_STYLE = {
  pass: "bg-emerald-50 text-emerald-700 border-emerald-200",
  flag: "bg-amber-50 text-amber-700 border-amber-200",
  fail: "bg-rose-50 text-rose-700 border-rose-200",
  pending: "bg-slate-50 text-slate-500 border-slate-200",
};

function summarize(items) {
  const total = items.length;
  const done = items.filter((i) => i.status !== "pending").length;
  const flagged = items.filter((i) => i.status === "flag" || i.status === "fail").length;
  return { total, done, flagged, complete: total > 0 && done === total };
}

export default function InspectionsList({ propertyId, unitId, inspectorName }) {
  const [inspections, setInspections] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState(null);
  const [creatingNew, setCreatingNew] = useState(false);
  const [error, setError] = useState(null);
  const { authFetch } = useAuth();

  const fetchInspections = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (propertyId) params.set("propertyId", propertyId);
      if (unitId) params.set("unitId", unitId);
      const res = await authFetch(`${API_BASE}/inspections?${params.toString()}`);
      if (res.ok) {
        const data = await res.json();
        setInspections(data.inspections || []);
      } else {
        setError(res.status === 403 ? "You don't have access to this." : "Couldn't load inspections — try again.");
      }
    } catch {
      setError("Couldn't load inspections — check your connection and try again.");
    } finally {
      setLoading(false);
    }
  }, [propertyId, unitId, authFetch]);

  useEffect(() => {
    if (!selectedId && !creatingNew) fetchInspections();
  }, [fetchInspections, selectedId, creatingNew]);

  if (creatingNew) {
    return (
      <InspectionChecklist
        propertyId={propertyId}
        unitId={unitId || "TBD"}
        inspectorName={inspectorName}
        onBack={() => setCreatingNew(false)}
      />
    );
  }

  if (selectedId) {
    return (
      <InspectionChecklist
        inspectionId={selectedId}
        propertyId={propertyId}
        unitId={unitId}
        inspectorName={inspectorName}
        onBack={() => setSelectedId(null)}
      />
    );
  }

  return (
    <div className="max-w-2xl mx-auto">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-lg font-semibold">Inspections</h2>
        <button
          onClick={() => setCreatingNew(true)}
          className="flex items-center gap-1.5 text-sm font-semibold bg-slate-900 text-white px-3 py-1.5 rounded-lg hover:bg-slate-800"
        >
          <Plus size={14} />
          New inspection
        </button>
      </div>

      {loading ? (
        <div className="h-40 bg-slate-100 rounded-xl animate-pulse" />
      ) : error ? (
        <p className="text-sm text-rose-600 bg-rose-50 border border-rose-200 rounded-xl px-4 py-3">{error}</p>
      ) : inspections.length === 0 ? (
        <EmptyState
          icon={ClipboardCheck}
          title="No inspections yet"
          subtitle="Inspections created here or auto-generated (like turnover checklists) will show up in this list."
        />
      ) : (
        <div className="space-y-2">
          {inspections.map((insp) => {
            const { total, done, flagged, complete } = summarize(insp.items || []);
            return (
              <button
                key={insp._id}
                onClick={() => setSelectedId(insp._id)}
                className="w-full text-left border border-slate-200 rounded-lg px-3 py-2.5 hover:border-slate-300 hover:bg-slate-50 transition-colors"
              >
                <div className="flex items-center justify-between">
                  <div>
                    <span className="text-sm font-medium">Unit {insp.unitId}</span>
                    <span className="text-xs text-slate-500 ml-2 capitalize">{insp.type} inspection</span>
                  </div>
                  <span
                    className={`text-[10px] font-mono uppercase px-2 py-0.5 rounded-full border ${
                      complete ? STATUS_STYLE.pass : STATUS_STYLE.pending
                    }`}
                  >
                    {done}/{total} complete
                  </span>
                </div>
                <div className="text-xs text-slate-500 mt-1 flex items-center gap-2">
                  {insp.createdAt ? new Date(insp.createdAt).toLocaleDateString() : ""}
                  {flagged > 0 && (
                    <span className="text-amber-700 font-mono">{flagged} flagged</span>
                  )}
                </div>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
