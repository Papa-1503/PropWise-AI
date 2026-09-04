import { useState, useEffect, useCallback, useId } from "react";
import { useAuth } from "./AuthContext";
import { useToast } from "./ToastContext";
import { API_BASE } from "./config";
import EmptyState from "./EmptyState";
import { Wrench, Plus, X, Star, AlertTriangle, Pencil } from "lucide-react";

/**
 * VendorsList
 *
 * The first real, standalone page for the vendor roster itself - the
 * backend (GET/POST/PATCH /api/vendors) already existed fully, but the
 * only frontend that ever called it was VendorAssignment.jsx, a
 * per-ticket picker with no way to see the whole roster, add a new
 * vendor, or update one's insurance/license dates. Also where the
 * real compliance alerts (backend/routers/admin.py's
 * _do_vendor_compliance_check) actually have somewhere to be seen and
 * acted on - a notification alone had nowhere in the UI to lead to.
 *
 * Deliberately limited to active vendors, matching the real
 * constraint already on GET /api/vendors (query hardcodes
 * active=true) - deactivating/reactivating a vendor is a separate,
 * distinct feature this doesn't attempt to add.
 */

const CATEGORIES = ["plumbing", "electrical", "hvac", "general", "landscaping", "locksmith"];

function complianceStatus(dateStr) {
  if (!dateStr) return null;
  const expires = new Date(dateStr);
  const now = new Date();
  const daysLeft = Math.floor((expires - now) / (1000 * 60 * 60 * 24));
  if (daysLeft < 0) return { label: "Expired", style: "bg-rose-50 text-rose-700 border-rose-200", daysLeft };
  if (daysLeft <= 30) return { label: `${daysLeft}d left`, style: "bg-amber-50 text-amber-700 border-amber-200", daysLeft };
  return null;
}

function VendorFormModal({ vendor, onClose, onSaved }) {
  const isEdit = !!vendor;
  const [name, setName] = useState(vendor?.name ?? "");
  const [category, setCategory] = useState(vendor?.category ?? "general");
  const [phone, setPhone] = useState(vendor?.phone ?? "");
  const [email, setEmail] = useState(vendor?.email ?? "");
  const [rating, setRating] = useState(vendor?.rating ?? 4.5);
  const [baseCost, setBaseCost] = useState(vendor?.baseCost ?? "");
  const [avgArrivalHours, setAvgArrivalHours] = useState(vendor?.avgArrivalHours ?? "");
  const [insuranceExpiresDate, setInsuranceExpiresDate] = useState(vendor?.insuranceExpiresDate?.slice(0, 10) ?? "");
  const [licenseNumber, setLicenseNumber] = useState(vendor?.licenseNumber ?? "");
  const [licenseExpiresDate, setLicenseExpiresDate] = useState(vendor?.licenseExpiresDate?.slice(0, 10) ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const { authFetch } = useAuth();
  const { show: showToast } = useToast();
  const idPrefix = useId();

  async function handleSave() {
    if (!name.trim()) {
      setError("A vendor name is required.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const body = {
        phone: phone || null,
        email: email || null,
        rating: rating === "" ? null : Number(rating),
        baseCost: baseCost === "" ? null : Number(baseCost),
        avgArrivalHours: avgArrivalHours === "" ? null : Number(avgArrivalHours),
        insuranceExpiresDate: insuranceExpiresDate || null,
        licenseNumber: licenseNumber || null,
        licenseExpiresDate: licenseExpiresDate || null,
      };
      let res;
      if (isEdit) {
        res = await authFetch(`${API_BASE}/vendors/${vendor.id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
      } else {
        res = await authFetch(`${API_BASE}/vendors`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name, category, ...body }),
        });
      }
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Something went wrong.");
      showToast(isEdit ? `Updated ${name}` : `Added ${name}`, "success");
      onSaved();
      onClose();
    } catch (err) {
      setError(err.message);
      showToast(err.message, "error");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-30 p-4">
      <div className="bg-white rounded-xl shadow-lg w-full max-w-md p-5 max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-semibold">{isEdit ? `Edit ${vendor.name}` : "New vendor"}</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600">
            <X size={18} />
          </button>
        </div>

        <div className="space-y-3">
          <div>
            <label htmlFor={`${idPrefix}-name`} className="text-xs text-slate-500">Name</label>
            <input
              id={`${idPrefix}-name`}
              value={name}
              onChange={(e) => setName(e.target.value)}
              disabled={isEdit}
              className="w-full text-sm border border-slate-200 rounded px-2 py-1.5 mt-0.5 disabled:bg-slate-50 disabled:text-slate-400"
            />
          </div>
          {!isEdit && (
            <div>
              <label htmlFor={`${idPrefix}-category`} className="text-xs text-slate-500">Category</label>
              <select
                id={`${idPrefix}-category`}
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                className="w-full text-sm border border-slate-200 rounded px-2 py-1.5 mt-0.5 capitalize"
              >
                {CATEGORIES.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </div>
          )}
          <div className="flex gap-3">
            <div className="flex-1">
              <label htmlFor={`${idPrefix}-phone`} className="text-xs text-slate-500">Phone</label>
              <input
                id={`${idPrefix}-phone`}
                type="tel"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                className="w-full text-sm border border-slate-200 rounded px-2 py-1.5 mt-0.5"
              />
            </div>
            <div className="flex-1">
              <label htmlFor={`${idPrefix}-email`} className="text-xs text-slate-500">Email</label>
              <input
                id={`${idPrefix}-email`}
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full text-sm border border-slate-200 rounded px-2 py-1.5 mt-0.5"
              />
            </div>
          </div>
          <div className="flex gap-3">
            <div className="flex-1">
              <label htmlFor={`${idPrefix}-rating`} className="text-xs text-slate-500">Rating (0-5)</label>
              <input
                id={`${idPrefix}-rating`}
                type="number" min="0" max="5" step="0.1"
                value={rating}
                onChange={(e) => setRating(e.target.value)}
                className="w-full text-sm border border-slate-200 rounded px-2 py-1.5 mt-0.5"
              />
            </div>
            <div className="flex-1">
              <label htmlFor={`${idPrefix}-cost`} className="text-xs text-slate-500">Base cost ($)</label>
              <input
                id={`${idPrefix}-cost`}
                type="number" min="0"
                value={baseCost}
                onChange={(e) => setBaseCost(e.target.value)}
                className="w-full text-sm border border-slate-200 rounded px-2 py-1.5 mt-0.5"
              />
            </div>
            <div className="flex-1">
              <label htmlFor={`${idPrefix}-arrival`} className="text-xs text-slate-500">Avg arrival (hrs)</label>
              <input
                id={`${idPrefix}-arrival`}
                type="number" min="0"
                value={avgArrivalHours}
                onChange={(e) => setAvgArrivalHours(e.target.value)}
                className="w-full text-sm border border-slate-200 rounded px-2 py-1.5 mt-0.5"
              />
            </div>
          </div>

          <div className="pt-2 border-t border-slate-100">
            <p className="text-xs text-slate-500 mb-2">
              Compliance dates feed the auto-dispatch gate and the automated expiration alerts.
            </p>
            <div className="flex gap-3">
              <div className="flex-1">
                <label htmlFor={`${idPrefix}-ins`} className="text-xs text-slate-500">Insurance expires</label>
                <input
                  id={`${idPrefix}-ins`}
                  type="date"
                  value={insuranceExpiresDate}
                  onChange={(e) => setInsuranceExpiresDate(e.target.value)}
                  className="w-full text-sm border border-slate-200 rounded px-2 py-1.5 mt-0.5"
                />
              </div>
              <div className="flex-1">
                <label htmlFor={`${idPrefix}-lic`} className="text-xs text-slate-500">License expires</label>
                <input
                  id={`${idPrefix}-lic`}
                  type="date"
                  value={licenseExpiresDate}
                  onChange={(e) => setLicenseExpiresDate(e.target.value)}
                  className="w-full text-sm border border-slate-200 rounded px-2 py-1.5 mt-0.5"
                />
              </div>
            </div>
            <div className="mt-3">
              <label htmlFor={`${idPrefix}-licnum`} className="text-xs text-slate-500">License number</label>
              <input
                id={`${idPrefix}-licnum`}
                value={licenseNumber}
                onChange={(e) => setLicenseNumber(e.target.value)}
                className="w-full text-sm border border-slate-200 rounded px-2 py-1.5 mt-0.5"
              />
            </div>
          </div>
        </div>

        {error && <p role="alert" className="text-xs text-rose-600 mt-3 bg-rose-50 border border-rose-200 rounded px-3 py-2">{error}</p>}

        <button
          onClick={handleSave}
          disabled={saving}
          className="mt-4 w-full bg-slate-900 disabled:bg-slate-300 text-white text-sm font-semibold py-2.5 rounded-lg hover:bg-slate-800"
        >
          {saving ? "Saving…" : isEdit ? "Save changes" : "Add vendor"}
        </button>
      </div>
    </div>
  );
}

export default function VendorsList() {
  const [vendors, setVendors] = useState(null);
  const [error, setError] = useState(null);
  const [category, setCategory] = useState("all");
  const [showNew, setShowNew] = useState(false);
  const [editingVendor, setEditingVendor] = useState(null);
  const { authFetch } = useAuth();

  const fetchVendors = useCallback(async () => {
    setError(null);
    try {
      const params = new URLSearchParams();
      if (category !== "all") params.set("category", category);
      const res = await authFetch(`${API_BASE}/vendors?${params.toString()}`);
      if (!res.ok) throw new Error("Couldn't load vendors.");
      const data = await res.json();
      setVendors(data.vendors || []);
    } catch (err) {
      setError(err.message);
    }
  }, [category, authFetch]);

  useEffect(() => {
    fetchVendors();
  }, [fetchVendors]);

  return (
    <div className="max-w-2xl mx-auto p-5 bg-white rounded-xl border border-slate-200">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-lg font-semibold">Vendors</h2>
        <button
          onClick={() => setShowNew(true)}
          className="flex items-center gap-1.5 text-sm font-semibold bg-slate-900 text-white px-3 py-1.5 rounded-lg hover:bg-slate-800"
        >
          <Plus size={14} />
          New vendor
        </button>
      </div>

      <div className="flex gap-1 mb-3 flex-wrap">
        {["all", ...CATEGORIES].map((c) => (
          <button
            key={c}
            onClick={() => setCategory(c)}
            className={`text-[11px] px-2.5 py-1 rounded-full border capitalize ${
              category === c ? "bg-slate-900 text-white border-slate-900" : "border-slate-200 text-slate-500"
            }`}
          >
            {c}
          </button>
        ))}
      </div>

      {error && (
        <p role="alert" className="text-sm text-rose-600 bg-rose-50 border border-rose-200 rounded-xl px-4 py-3">
          {error}
        </p>
      )}

      {!error && vendors === null && <div className="h-32 bg-slate-100 rounded-xl animate-pulse" />}

      {!error && vendors !== null && vendors.length === 0 && (
        <EmptyState
          icon={Wrench}
          title="No vendors yet"
          subtitle="Add your first vendor to start assigning them to maintenance tickets."
        />
      )}

      {!error && vendors && vendors.length > 0 && (
        <div className="space-y-2">
          {vendors.map((v) => {
            const insurance = complianceStatus(v.insuranceExpiresDate);
            const license = complianceStatus(v.licenseExpiresDate);
            return (
              <div key={v.id} className="border border-slate-200 rounded-lg px-3 py-2.5">
                <div className="flex items-center justify-between">
                  <div>
                    <span className="text-sm font-medium">{v.name}</span>
                    <span className="text-xs text-slate-400 ml-2 capitalize">{v.category}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="flex items-center gap-0.5 text-xs text-amber-600">
                      <Star size={11} fill="currentColor" />
                      {v.rating?.toFixed(1) ?? "—"}
                    </span>
                    <button
                      onClick={() => setEditingVendor(v)}
                      className="text-slate-400 hover:text-indigo-600"
                      title="Edit vendor"
                    >
                      <Pencil size={13} />
                    </button>
                  </div>
                </div>
                <p className="text-xs text-slate-500 mt-1">
                  {v.phone || "No phone"} {v.email ? `· ${v.email}` : ""}
                  {v.baseCost != null && ` · ~$${v.baseCost}`}
                  {v.avgArrivalHours != null && ` · ~${v.avgArrivalHours}h arrival`}
                </p>
                {(insurance || license) && (
                  <div className="flex gap-1.5 mt-1.5">
                    {insurance && (
                      <span className={`flex items-center gap-1 text-[10px] font-mono uppercase px-2 py-0.5 rounded-full border ${insurance.style}`}>
                        <AlertTriangle size={10} />
                        Insurance {insurance.label}
                      </span>
                    )}
                    {license && (
                      <span className={`flex items-center gap-1 text-[10px] font-mono uppercase px-2 py-0.5 rounded-full border ${license.style}`}>
                        <AlertTriangle size={10} />
                        License {license.label}
                      </span>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {showNew && <VendorFormModal onClose={() => setShowNew(false)} onSaved={fetchVendors} />}
      {editingVendor && (
        <VendorFormModal vendor={editingVendor} onClose={() => setEditingVendor(null)} onSaved={fetchVendors} />
      )}
    </div>
  );
}
