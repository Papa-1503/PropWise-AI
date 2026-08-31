import { useState, useEffect, useCallback } from "react";
import { useAuth } from "./AuthContext";
import EmptyState from "./EmptyState";
import { Tag, Plus, X } from "lucide-react";
import { API_BASE } from "./config";

const ENTITY_TYPES = ["unit", "lease", "vendor", "ticket"];
const FIELD_TYPES = ["text", "number", "boolean", "date"];

export default function CustomFields() {
  const [entityType, setEntityType] = useState("unit");
  const [definitions, setDefinitions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showNew, setShowNew] = useState(false);
  const { authFetch } = useAuth();

  const fetchDefinitions = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await authFetch(`${API_BASE}/custom-fields/definitions?entityType=${entityType}`);
      if (!res.ok) throw new Error("Couldn't load field definitions.");
      const data = await res.json();
      setDefinitions(data.definitions || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [entityType, authFetch]);

  useEffect(() => {
    fetchDefinitions();
  }, [fetchDefinitions]);

  return (
    <div className="max-w-2xl mx-auto">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-lg font-semibold">Custom Fields</h2>
        <button
          onClick={() => setShowNew(true)}
          className="flex items-center gap-1.5 text-sm font-semibold bg-slate-900 text-white px-3 py-1.5 rounded-lg hover:bg-slate-800"
        >
          <Plus size={14} /> New field
        </button>
      </div>

      <div className="flex gap-1.5 mb-3">
        {ENTITY_TYPES.map((t) => (
          <button
            key={t}
            onClick={() => setEntityType(t)}
            className={`text-xs font-medium px-2.5 py-1 rounded-full border capitalize ${
              entityType === t ? "bg-indigo-600 text-white border-indigo-600" : "bg-white text-slate-600 border-slate-200"
            }`}
          >
            {t}s
          </button>
        ))}
      </div>

      {loading && <div className="text-sm text-slate-500">Loading...</div>}
      {error && <div className="text-sm text-rose-600 bg-rose-50 border border-rose-200 rounded-lg p-3" role="alert">{error}</div>}

      {!loading && !error && definitions.length === 0 && (
        <EmptyState icon={Tag} title={`No custom fields for ${entityType}s`} subtitle="Define a field to track something this app doesn't have a built-in field for." />
      )}

      {!loading && !error && definitions.length > 0 && (
        <div className="space-y-2">
          {definitions.map((d) => (
            <div key={d.id} className="bg-white border border-slate-200 rounded-lg p-3 flex items-center justify-between">
              <span className="text-sm font-medium">{d.fieldName}</span>
              <div className="flex items-center gap-2">
                <span className="text-xs text-slate-500 capitalize">{d.fieldType}</span>
                {d.required && <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-amber-50 text-amber-600">required</span>}
              </div>
            </div>
          ))}
        </div>
      )}

      {showNew && (
        <NewFieldModal
          entityType={entityType}
          onClose={() => setShowNew(false)}
          onSaved={fetchDefinitions}
        />
      )}
    </div>
  );
}

function NewFieldModal({ entityType, onClose, onSaved }) {
  const [fieldName, setFieldName] = useState("");
  const [fieldType, setFieldType] = useState("text");
  const [required, setRequired] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const { authFetch } = useAuth();

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      const res = await authFetch(`${API_BASE}/custom-fields/definitions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ entityType, fieldName, fieldType, required }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Couldn't save the field.");
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
      <div className="bg-white rounded-xl p-5 w-full max-w-sm">
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-semibold">New field for {entityType}s</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600"><X size={18} /></button>
        </div>
        {error && <p className="text-sm text-rose-600 mb-2" role="alert">{error}</p>}
        <div className="space-y-2">
          <input
            value={fieldName}
            onChange={(e) => setFieldName(e.target.value)}
            placeholder="Field name (e.g. parkingSpots)"
            className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
          />
          <select
            value={fieldType}
            onChange={(e) => setFieldType(e.target.value)}
            className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
          >
            {FIELD_TYPES.map((t) => <option key={t} value={t} className="capitalize">{t}</option>)}
          </select>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={required} onChange={(e) => setRequired(e.target.checked)} />
            Required
          </label>
        </div>
        <button
          onClick={handleSave}
          disabled={saving || !fieldName}
          className="w-full mt-3 bg-slate-900 text-white rounded-lg py-2 text-sm font-semibold hover:bg-slate-800 disabled:opacity-50"
        >
          {saving ? "Saving..." : "Save field"}
        </button>
      </div>
    </div>
  );
}
