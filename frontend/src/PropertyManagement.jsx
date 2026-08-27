import { useState, useEffect, useCallback, useId } from "react";
import { useAuth } from "./AuthContext";
import { Building2, Plus, X, Pencil } from "lucide-react";
import { API_BASE } from "./config";

/**
 * PropertyManagement
 *
 * Priority 48 — least urgent of the six frontend gaps found in today's
 * sweep (creating a whole property is rare), but real: no UI existed
 * to create a property, edit one's name/address, add a unit to an
 * existing property, or edit a unit's rent/bed/bath after creation.
 *
 * Building this also surfaced and fixed real backend gaps: PropertyUpdate
 * was a defined model with zero endpoint using it, and no endpoint
 * existed at all for adding a unit or editing unit details (only unit
 * *status* could be changed) — all three added alongside this UI.
 */

function NewPropertyModal({ onClose, onSaved }) {
  const [name, setName] = useState("");
  const [address, setAddress] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const { authFetch } = useAuth();
  const idPrefix = useId();

  async function handleSave() {
    if (!name.trim()) {
      setError("A property name is required.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const res = await authFetch(`${API_BASE}/properties`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, address, units: [] }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Something went wrong");
      onSaved();
      onClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-30 p-4">
      <div className="bg-white rounded-xl shadow-lg w-full max-w-md p-5">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-semibold">New property</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600">
            <X size={18} />
          </button>
        </div>

        <div className="space-y-3">
          <div>
            <label htmlFor={`${idPrefix}-name`} className="text-xs text-slate-500">Property name</label>
            <input
              id={`${idPrefix}-name`}
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full text-sm border border-slate-200 rounded px-2 py-1.5 mt-0.5"
            />
          </div>
          <div>
            <label htmlFor={`${idPrefix}-address`} className="text-xs text-slate-500">Address</label>
            <input
              id={`${idPrefix}-address`}
              autoComplete="street-address"
              value={address}
              onChange={(e) => setAddress(e.target.value)}
              className="w-full text-sm border border-slate-200 rounded px-2 py-1.5 mt-0.5"
            />
          </div>
        </div>

        {error && <p role="alert" className="text-xs text-rose-600 mt-3 bg-rose-50 border border-rose-200 rounded px-3 py-2">{error}</p>}

        <button
          onClick={handleSave}
          disabled={saving}
          className="mt-4 w-full bg-slate-900 disabled:bg-slate-300 text-white text-sm font-semibold py-2.5 rounded-lg hover:bg-slate-800"
        >
          {saving ? "Creating…" : "Create property"}
        </button>
        <p className="text-[11px] text-slate-400 mt-2">Units can be added afterward, from the property's row below.</p>
      </div>
    </div>
  );
}

function AddUnitModal({ property, onClose, onSaved }) {
  const [unitId, setUnitId] = useState("");
  const [rent, setRent] = useState("");
  const [bedrooms, setBedrooms] = useState("");
  const [bathrooms, setBathrooms] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const { authFetch } = useAuth();
  const idPrefix = useId();

  async function handleSave() {
    if (!unitId.trim()) {
      setError("A unit number/ID is required.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const res = await authFetch(`${API_BASE}/properties/${property.id}/units`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          unitId,
          rent: rent ? Number(rent) : 0,
          bedrooms: bedrooms ? Number(bedrooms) : 0,
          bathrooms: bathrooms ? Number(bathrooms) : 0,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Something went wrong");
      onSaved();
      onClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-30 p-4">
      <div className="bg-white rounded-xl shadow-lg w-full max-w-md p-5">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-semibold">Add unit to {property.name}</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600">
            <X size={18} />
          </button>
        </div>

        <div className="space-y-3">
          <div>
            <label htmlFor={`${idPrefix}-unit`} className="text-xs text-slate-500">Unit number</label>
            <input id={`${idPrefix}-unit`} value={unitId} onChange={(e) => setUnitId(e.target.value)} className="w-full text-sm border border-slate-200 rounded px-2 py-1.5 mt-0.5" />
          </div>
          <div className="flex gap-3">
            <div className="flex-1">
              <label htmlFor={`${idPrefix}-rent`} className="text-xs text-slate-500">Rent</label>
              <input id={`${idPrefix}-rent`} type="number" value={rent} onChange={(e) => setRent(e.target.value)} className="w-full text-sm border border-slate-200 rounded px-2 py-1.5 mt-0.5" />
            </div>
            <div className="flex-1">
              <label htmlFor={`${idPrefix}-bed`} className="text-xs text-slate-500">Bedrooms</label>
              <input id={`${idPrefix}-bed`} type="number" value={bedrooms} onChange={(e) => setBedrooms(e.target.value)} className="w-full text-sm border border-slate-200 rounded px-2 py-1.5 mt-0.5" />
            </div>
            <div className="flex-1">
              <label htmlFor={`${idPrefix}-bath`} className="text-xs text-slate-500">Bathrooms</label>
              <input id={`${idPrefix}-bath`} type="number" step="0.5" value={bathrooms} onChange={(e) => setBathrooms(e.target.value)} className="w-full text-sm border border-slate-200 rounded px-2 py-1.5 mt-0.5" />
            </div>
          </div>
        </div>

        {error && <p role="alert" className="text-xs text-rose-600 mt-3 bg-rose-50 border border-rose-200 rounded px-3 py-2">{error}</p>}

        <button
          onClick={handleSave}
          disabled={saving}
          className="mt-4 w-full bg-slate-900 disabled:bg-slate-300 text-white text-sm font-semibold py-2.5 rounded-lg hover:bg-slate-800"
        >
          {saving ? "Adding…" : "Add unit"}
        </button>
      </div>
    </div>
  );
}

function EditUnitModal({ property, unit, onClose, onSaved }) {
  const [rent, setRent] = useState(unit.rent ?? "");
  const [bedrooms, setBedrooms] = useState(unit.bedrooms ?? "");
  const [bathrooms, setBathrooms] = useState(unit.bathrooms ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const { authFetch } = useAuth();
  const idPrefix = useId();

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      const res = await authFetch(`${API_BASE}/properties/${property.id}/units/${unit.unitId}/details`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          rent: rent === "" ? null : Number(rent),
          bedrooms: bedrooms === "" ? null : Number(bedrooms),
          bathrooms: bathrooms === "" ? null : Number(bathrooms),
        }),
      });
      if (!res.ok) throw new Error("Couldn't save changes.");
      onSaved();
      onClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-30 p-4">
      <div className="bg-white rounded-xl shadow-lg w-full max-w-md p-5">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-semibold">Edit Unit {unit.unitId}</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600">
            <X size={18} />
          </button>
        </div>
        <div className="flex gap-3">
          <div className="flex-1">
            <label htmlFor={`${idPrefix}-rent`} className="text-xs text-slate-500">Rent</label>
            <input id={`${idPrefix}-rent`} type="number" value={rent} onChange={(e) => setRent(e.target.value)} className="w-full text-sm border border-slate-200 rounded px-2 py-1.5 mt-0.5" />
          </div>
          <div className="flex-1">
            <label htmlFor={`${idPrefix}-bed`} className="text-xs text-slate-500">Bedrooms</label>
            <input id={`${idPrefix}-bed`} type="number" value={bedrooms} onChange={(e) => setBedrooms(e.target.value)} className="w-full text-sm border border-slate-200 rounded px-2 py-1.5 mt-0.5" />
          </div>
          <div className="flex-1">
            <label htmlFor={`${idPrefix}-bath`} className="text-xs text-slate-500">Bathrooms</label>
            <input id={`${idPrefix}-bath`} type="number" step="0.5" value={bathrooms} onChange={(e) => setBathrooms(e.target.value)} className="w-full text-sm border border-slate-200 rounded px-2 py-1.5 mt-0.5" />
          </div>
        </div>
        {error && <p role="alert" className="text-xs text-rose-600 mt-3 bg-rose-50 border border-rose-200 rounded px-3 py-2">{error}</p>}
        <button
          onClick={handleSave}
          disabled={saving}
          className="mt-4 w-full bg-slate-900 disabled:bg-slate-300 text-white text-sm font-semibold py-2.5 rounded-lg hover:bg-slate-800"
        >
          {saving ? "Saving…" : "Save changes"}
        </button>
      </div>
    </div>
  );
}

export default function PropertyManagement() {
  const [properties, setProperties] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showNewProperty, setShowNewProperty] = useState(false);
  const [addUnitTo, setAddUnitTo] = useState(null); // property | null
  const [editingUnit, setEditingUnit] = useState(null); // { property, unit } | null
  const { authFetch } = useAuth();

  const fetchProperties = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await authFetch(`${API_BASE}/properties`);
      if (res.ok) {
        const data = await res.json();
        setProperties(data.properties || []);
      } else {
        setError(res.status === 403 ? "You don't have access to this." : "Couldn't load properties — try again.");
      }
    } catch {
      setError("Couldn't load properties — check your connection and try again.");
    } finally {
      setLoading(false);
    }
  }, [authFetch]);

  useEffect(() => {
    fetchProperties();
  }, [fetchProperties]);

  return (
    <div className="max-w-2xl mx-auto">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-lg font-semibold">Properties</h2>
        <button
          onClick={() => setShowNewProperty(true)}
          className="flex items-center gap-1.5 text-sm font-semibold bg-slate-900 text-white px-3 py-1.5 rounded-lg hover:bg-slate-800"
        >
          <Plus size={14} />
          New property
        </button>
      </div>

      {loading ? (
        <div className="h-40 bg-slate-100 rounded-xl animate-pulse" />
      ) : error ? (
        <p role="alert" aria-live="polite" className="text-sm text-rose-600 bg-rose-50 border border-rose-200 rounded-xl px-4 py-3">{error}</p>
      ) : properties.length === 0 ? (
        <p className="text-sm text-slate-400 flex items-center gap-2"><Building2 size={16} /> No properties yet.</p>
      ) : (
        <div className="space-y-3">
          {properties.map((p) => (
            <div key={p.id} className="bg-white border border-slate-200 rounded-xl p-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-semibold">{p.name}</span>
                <button
                  onClick={() => setAddUnitTo(p)}
                  className="flex items-center gap-1 text-[11px] text-indigo-700 hover:underline"
                >
                  <Plus size={12} />
                  Add unit
                </button>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {(p.units || []).map((u) => (
                  <button
                    key={u.unitId}
                    onClick={() => setEditingUnit({ property: p, unit: u })}
                    className="flex items-center gap-1 text-[11px] px-2 py-1 rounded-full border bg-slate-50 text-slate-600 border-slate-200 hover:border-indigo-300"
                    title="Click to edit rent/bed/bath"
                  >
                    {u.unitId}
                    <Pencil size={9} />
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {showNewProperty && (
        <NewPropertyModal onClose={() => setShowNewProperty(false)} onSaved={fetchProperties} />
      )}
      {addUnitTo && (
        <AddUnitModal property={addUnitTo} onClose={() => setAddUnitTo(null)} onSaved={fetchProperties} />
      )}
      {editingUnit && (
        <EditUnitModal
          property={editingUnit.property}
          unit={editingUnit.unit}
          onClose={() => setEditingUnit(null)}
          onSaved={fetchProperties}
        />
      )}
    </div>
  );
}
