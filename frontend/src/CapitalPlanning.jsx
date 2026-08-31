import { useState, useEffect, useCallback } from "react";
import { useAuth } from "./AuthContext";
import EmptyState from "./EmptyState";
import { Wrench, Plus, X, AlertTriangle } from "lucide-react";
import { API_BASE } from "./config";

export default function CapitalPlanning({ propertyId }) {
  const [tab, setTab] = useState("assets");

  return (
    <div className="max-w-2xl mx-auto">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-lg font-semibold">Capital Planning</h2>
      </div>
      <div className="flex gap-1.5 mb-3">
        {["assets", "projects"].map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`text-xs font-medium px-2.5 py-1 rounded-full border ${
              tab === t ? "bg-indigo-600 text-white border-indigo-600" : "bg-white text-slate-600 border-slate-200"
            }`}
          >
            {t === "assets" ? "Fixed Assets" : "Capital Projects"}
          </button>
        ))}
      </div>
      {tab === "assets" ? <FixedAssetsTab propertyId={propertyId} /> : <CapitalProjectsTab propertyId={propertyId} />}
    </div>
  );
}

function FixedAssetsTab({ propertyId }) {
  const [assets, setAssets] = useState([]);
  const [endOfLife, setEndOfLife] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showNew, setShowNew] = useState(false);
  const { authFetch } = useAuth();

  const fetchAssets = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (propertyId) params.set("propertyId", propertyId);
      const [listRes, eolRes] = await Promise.all([
        authFetch(`${API_BASE}/fixed-assets?${params.toString()}`),
        authFetch(`${API_BASE}/fixed-assets/end-of-life?${params.toString()}`),
      ]);
      if (!listRes.ok) throw new Error("Couldn't load fixed assets.");
      const listData = await listRes.json();
      const eolData = await eolRes.json().catch(() => ({ assets: [] }));
      setAssets(listData.assets || []);
      setEndOfLife(eolData.assets || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [propertyId, authFetch]);

  useEffect(() => {
    fetchAssets();
  }, [fetchAssets]);

  return (
    <div>
      <button
        onClick={() => setShowNew(true)}
        className="flex items-center gap-1.5 text-sm font-semibold bg-slate-900 text-white px-3 py-1.5 rounded-lg hover:bg-slate-800 mb-3"
      >
        <Plus size={14} /> New asset
      </button>

      {loading && <div className="text-sm text-slate-500">Loading...</div>}
      {error && <div className="text-sm text-rose-600 bg-rose-50 border border-rose-200 rounded-lg p-3" role="alert">{error}</div>}

      {!loading && !error && endOfLife.length > 0 && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 mb-3">
          <div className="flex items-center gap-2 mb-2">
            <AlertTriangle size={16} className="text-amber-600" />
            <h3 className="text-sm font-semibold text-amber-800">Approaching end of life ({endOfLife.length})</h3>
          </div>
          <div className="space-y-1.5">
            {endOfLife.map((a) => (
              <div key={a.id} className="text-sm flex justify-between">
                <span>{a.name}</span>
                <span className={a.pastEndOfLife ? "text-rose-600 font-medium" : "text-amber-700"}>
                  {a.pastEndOfLife ? "Past due" : `${a.yearsRemaining.toFixed(1)}y left`}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {!loading && !error && assets.length === 0 && (
        <EmptyState icon={Wrench} title="No fixed assets" subtitle="Track roofs, HVAC systems, water heaters, and more." />
      )}

      {!loading && !error && assets.length > 0 && (
        <div className="space-y-2">
          {assets.map((a) => (
            <div key={a.id} className="bg-white border border-slate-200 rounded-lg p-3">
              <p className="text-sm font-medium">{a.name}</p>
              <p className="text-xs text-slate-500">
                {a.category} · installed {new Date(a.installDate).toLocaleDateString()} · {a.expectedLifespanYears}y expected life
              </p>
            </div>
          ))}
        </div>
      )}

      {showNew && <NewAssetModal propertyId={propertyId} onClose={() => setShowNew(false)} onSaved={fetchAssets} />}
    </div>
  );
}

function NewAssetModal({ propertyId, onClose, onSaved }) {
  const [name, setName] = useState("");
  const [category, setCategory] = useState("");
  const [installDate, setInstallDate] = useState("");
  const [expectedLifespanYears, setExpectedLifespanYears] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const { authFetch } = useAuth();

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      const res = await authFetch(`${API_BASE}/fixed-assets`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ propertyId, name, category, installDate, expectedLifespanYears: Number(expectedLifespanYears) }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Couldn't save the asset.");
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
          <h3 className="font-semibold">New fixed asset</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600"><X size={18} /></button>
        </div>
        {error && <p className="text-sm text-rose-600 mb-2" role="alert">{error}</p>}
        <div className="space-y-2">
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Name (e.g. Roof)" className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" />
          <input value={category} onChange={(e) => setCategory(e.target.value)} placeholder="Category (e.g. roofing)" className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" />
          <div>
            <label className="text-xs text-slate-500">Install date</label>
            <input type="date" value={installDate} onChange={(e) => setInstallDate(e.target.value)} className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm mt-1" />
          </div>
          <div>
            <label className="text-xs text-slate-500">Expected lifespan (years)</label>
            <input type="number" min="0" value={expectedLifespanYears} onChange={(e) => setExpectedLifespanYears(e.target.value)} className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm mt-1" />
          </div>
        </div>
        <button
          onClick={handleSave}
          disabled={saving || !name || !category || !installDate || !expectedLifespanYears}
          className="w-full mt-3 bg-slate-900 text-white rounded-lg py-2 text-sm font-semibold hover:bg-slate-800 disabled:opacity-50"
        >
          {saving ? "Saving..." : "Save asset"}
        </button>
      </div>
    </div>
  );
}

function CapitalProjectsTab({ propertyId }) {
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showNew, setShowNew] = useState(false);
  const { authFetch } = useAuth();

  const fetchProjects = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (propertyId) params.set("propertyId", propertyId);
      const res = await authFetch(`${API_BASE}/capital-projects?${params.toString()}`);
      if (!res.ok) throw new Error("Couldn't load capital projects.");
      const data = await res.json();
      setProjects(data.projects || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [propertyId, authFetch]);

  useEffect(() => {
    fetchProjects();
  }, [fetchProjects]);

  return (
    <div>
      <button
        onClick={() => setShowNew(true)}
        className="flex items-center gap-1.5 text-sm font-semibold bg-slate-900 text-white px-3 py-1.5 rounded-lg hover:bg-slate-800 mb-3"
      >
        <Plus size={14} /> New project
      </button>

      {loading && <div className="text-sm text-slate-500">Loading...</div>}
      {error && <div className="text-sm text-rose-600 bg-rose-50 border border-rose-200 rounded-lg p-3" role="alert">{error}</div>}

      {!loading && !error && projects.length === 0 && (
        <EmptyState icon={Wrench} title="No capital projects" subtitle="Plan larger, budgeted improvements ahead of time." />
      )}

      {!loading && !error && projects.length > 0 && (
        <div className="space-y-2">
          {projects.map((p) => (
            <div key={p.id} className="bg-white border border-slate-200 rounded-lg p-3">
              <div className="flex justify-between">
                <p className="text-sm font-medium">{p.title}</p>
                <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-slate-100 text-slate-600">{p.status}</span>
              </div>
              <p className="text-xs text-slate-500">
                ${p.projectedCost.toLocaleString()} · target {new Date(p.targetDate).toLocaleDateString()}
              </p>
            </div>
          ))}
        </div>
      )}

      {showNew && <NewProjectModal propertyId={propertyId} onClose={() => setShowNew(false)} onSaved={fetchProjects} />}
    </div>
  );
}

function NewProjectModal({ propertyId, onClose, onSaved }) {
  const [title, setTitle] = useState("");
  const [projectedCost, setProjectedCost] = useState("");
  const [targetDate, setTargetDate] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const { authFetch } = useAuth();

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      const res = await authFetch(`${API_BASE}/capital-projects`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ propertyId, title, projectedCost: Number(projectedCost), targetDate }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Couldn't save the project.");
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
          <h3 className="font-semibold">New capital project</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600"><X size={18} /></button>
        </div>
        {error && <p className="text-sm text-rose-600 mb-2" role="alert">{error}</p>}
        <div className="space-y-2">
          <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Project title" className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" />
          <input type="number" min="0" value={projectedCost} onChange={(e) => setProjectedCost(e.target.value)} placeholder="Projected cost ($)" className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" />
          <div>
            <label className="text-xs text-slate-500">Target date</label>
            <input type="date" value={targetDate} onChange={(e) => setTargetDate(e.target.value)} className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm mt-1" />
          </div>
        </div>
        <button
          onClick={handleSave}
          disabled={saving || !title || !projectedCost || !targetDate}
          className="w-full mt-3 bg-slate-900 text-white rounded-lg py-2 text-sm font-semibold hover:bg-slate-800 disabled:opacity-50"
        >
          {saving ? "Saving..." : "Save project"}
        </button>
      </div>
    </div>
  );
}
