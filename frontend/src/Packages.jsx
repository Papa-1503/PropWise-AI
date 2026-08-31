import { useState, useEffect, useCallback } from "react";
import { useAuth } from "./AuthContext";
import EmptyState from "./EmptyState";
import { Package, Camera, X, Check } from "lucide-react";
import { API_BASE } from "./config";

/**
 * Packages
 *
 * Real frontend for backend/routers/package_tracking.py, built this
 * session but never given a UI until now - the genuine gap the Form
 * Library surfaced honestly rather than silently pointing staff at
 * an unrelated tab. Front-desk logs an arrived package (optionally
 * scanning the label photo for a real OCR-assisted read, always
 * staff-confirmed before saving - see the backend's own docstring for
 * why), and marks pickup once the resident collects it.
 */
export default function Packages({ propertyId }) {
  const [packages, setPackages] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showNew, setShowNew] = useState(false);
  const [filter, setFilter] = useState("pending");
  const { authFetch } = useAuth();

  const fetchPackages = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (propertyId) params.set("propertyId", propertyId);
      if (filter === "pending") params.set("pickedUp", "false");
      if (filter === "pickedUp") params.set("pickedUp", "true");
      const res = await authFetch(`${API_BASE}/packages?${params.toString()}`);
      if (!res.ok) throw new Error("Couldn't load packages.");
      const data = await res.json();
      setPackages(data.packages || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [propertyId, filter, authFetch]);

  useEffect(() => {
    fetchPackages();
  }, [fetchPackages]);

  async function markPickedUp(pkg) {
    const pickedUpBy = window.prompt("Who picked this up? (name)");
    if (!pickedUpBy) return;
    const res = await authFetch(`${API_BASE}/packages/${pkg.id}/pickup`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pickedUpBy }),
    });
    if (res.ok) fetchPackages();
  }

  return (
    <div className="max-w-2xl mx-auto">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-lg font-semibold">Packages</h2>
        <button
          onClick={() => setShowNew(true)}
          className="flex items-center gap-1.5 text-sm font-semibold bg-slate-900 text-white px-3 py-1.5 rounded-lg hover:bg-slate-800"
        >
          <Package size={14} />
          Log package
        </button>
      </div>

      <div className="flex gap-1.5 mb-3">
        {["pending", "pickedUp", "all"].map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`text-xs font-medium px-2.5 py-1 rounded-full border ${
              filter === f ? "bg-indigo-600 text-white border-indigo-600" : "bg-white text-slate-600 border-slate-200"
            }`}
          >
            {f === "pending" ? "Awaiting pickup" : f === "pickedUp" ? "Picked up" : "All"}
          </button>
        ))}
      </div>

      {loading && <div className="text-sm text-slate-500">Loading...</div>}
      {error && (
        <div className="text-sm text-rose-600 bg-rose-50 border border-rose-200 rounded-lg p-3 mb-3" role="alert">
          {error}
        </div>
      )}

      {!loading && !error && packages.length === 0 && (
        <EmptyState icon={Package} title="No packages" subtitle="Logged packages will show up here." />
      )}

      {!loading && !error && packages.length > 0 && (
        <div className="space-y-2">
          {packages.map((pkg) => (
            <div key={pkg.id} className="bg-white border border-slate-200 rounded-lg p-3 flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-slate-800">
                  Unit {pkg.unitId || "—"} {pkg.residentName && `· ${pkg.residentName}`}
                </p>
                <p className="text-xs text-slate-500">
                  {pkg.carrier || "Unknown carrier"} · logged {new Date(pkg.loggedAt).toLocaleDateString()}
                </p>
              </div>
              {pkg.pickedUp ? (
                <span className="flex items-center gap-1 text-xs text-emerald-600 font-medium">
                  <Check size={13} /> Picked up
                </span>
              ) : (
                <button
                  onClick={() => markPickedUp(pkg)}
                  className="text-xs font-semibold text-indigo-600 hover:underline"
                >
                  Mark picked up
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      {showNew && (
        <NewPackageModal
          propertyId={propertyId}
          onClose={() => setShowNew(false)}
          onSaved={fetchPackages}
        />
      )}
    </div>
  );
}

function NewPackageModal({ propertyId, onClose, onSaved }) {
  const [unitId, setUnitId] = useState("");
  const [residentName, setResidentName] = useState("");
  const [carrier, setCarrier] = useState("");
  const [scanning, setScanning] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const { authFetch } = useAuth();

  async function handlePhotoScan(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setScanning(true);
    setError(null);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await authFetch(`${API_BASE}/packages/log-with-photo`, { method: "POST", body: formData });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Couldn't read the label.");
      if (data.extracted?.unitId) setUnitId(data.extracted.unitId);
      if (data.extracted?.residentName) setResidentName(data.extracted.residentName);
      if (data.extracted?.carrier) setCarrier(data.extracted.carrier);
    } catch (err) {
      setError(err.message);
    } finally {
      setScanning(false);
    }
  }

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      const res = await authFetch(`${API_BASE}/packages`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ propertyId, unitId: unitId || null, residentName: residentName || null, carrier: carrier || null }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Couldn't log the package.");
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
          <h3 className="font-semibold">Log a package</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600"><X size={18} /></button>
        </div>

        {error && <p className="text-sm text-rose-600 mb-2" role="alert">{error}</p>}

        <label className="flex items-center justify-center gap-2 text-sm font-medium text-indigo-600 border-2 border-dashed border-indigo-200 rounded-lg py-3 mb-3 cursor-pointer hover:bg-indigo-50">
          <Camera size={16} />
          {scanning ? "Reading label..." : "Scan the label (optional)"}
          <input type="file" accept="image/*" className="hidden" onChange={handlePhotoScan} disabled={scanning} />
        </label>

        <div className="space-y-2">
          <input
            value={unitId}
            onChange={(e) => setUnitId(e.target.value)}
            placeholder="Unit (optional)"
            className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
          />
          <input
            value={residentName}
            onChange={(e) => setResidentName(e.target.value)}
            placeholder="Resident name (optional)"
            className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
          />
          <input
            value={carrier}
            onChange={(e) => setCarrier(e.target.value)}
            placeholder="Carrier (optional)"
            className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
          />
        </div>

        <button
          onClick={handleSave}
          disabled={saving}
          className="w-full mt-3 bg-slate-900 text-white rounded-lg py-2 text-sm font-semibold hover:bg-slate-800 disabled:opacity-50"
        >
          {saving ? "Saving..." : "Log package"}
        </button>
      </div>
    </div>
  );
}
