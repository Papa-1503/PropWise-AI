import { useState } from "react";
import { useAuth } from "./AuthContext";
import { Building2, ChevronDown, Check } from "lucide-react";

/**
 * BuildingSelector
 *
 * Staff-only dropdown that sets the app's active building context.
 * "All Buildings" (selectedProperty = null) aggregates across the whole
 * portfolio, same as the previous default behavior. Picking a specific
 * building scopes every panel (Dashboard, Maintenance, Payments,
 * Inspections, etc.) to just that property, so a unit number like "101"
 * — which many buildings share — is never ambiguous about which
 * building it belongs to.
 */
export default function BuildingSelector() {
  const { properties, selectedProperty, setSelectedProperty } = useAuth();
  const [open, setOpen] = useState(false);

  if (properties.length === 0) return null;

  const label = selectedProperty ? selectedProperty.name : "All Buildings";

  function choose(prop) {
    setSelectedProperty(prop);
    setOpen(false);
  }

  return (
    <div data-onboarding-target="building-selector" className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1.5 text-sm bg-white/10 hover:bg-white/20 text-white border border-white/25 rounded-full px-3 py-1.5 transition-colors"
      >
        <Building2 size={14} />
        <span className="font-medium max-w-[180px] truncate">{label}</span>
        <ChevronDown size={14} className={`transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div className="absolute right-0 top-11 bg-white border border-slate-200 rounded-xl shadow-lg py-1.5 w-64 max-h-96 overflow-y-auto z-20">
            <button
              onClick={() => choose(null)}
              className="w-full text-left text-sm px-3 py-2 flex items-center justify-between hover:bg-slate-50"
            >
              <span className={!selectedProperty ? "font-semibold text-indigo-600" : "text-slate-700"}>
                All Buildings
              </span>
              {!selectedProperty && <Check size={14} className="text-indigo-600" />}
            </button>
            <div className="border-t border-slate-100 my-1" />
            {properties.map((p) => (
              <button
                key={p.id}
                onClick={() => choose(p)}
                className="w-full text-left text-sm px-3 py-2 flex items-center justify-between hover:bg-slate-50"
              >
                <span className={selectedProperty?.id === p.id ? "font-semibold text-indigo-600" : "text-slate-700"}>
                  {p.name}
                </span>
                {selectedProperty?.id === p.id && <Check size={14} className="text-indigo-600" />}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
