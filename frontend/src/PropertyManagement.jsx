import { useState, useEffect, useCallback, useId, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { useAuth } from "./AuthContext";
import { Building2, Plus, X, Pencil, Search, Settings2, Phone } from "lucide-react";
import { useToast } from "./ToastContext";
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

function RentRulesModal({ property, onClose, onSaved }) {
  const [graceDays, setGraceDays] = useState(property.lateFeeGraceDays ?? "");
  const [feeAmount, setFeeAmount] = useState(property.lateFeeAmount ?? "");
  const [dueDay, setDueDay] = useState(property.dueDay ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const { authFetch } = useAuth();
  const { show: showToast } = useToast();
  const idPrefix = useId();

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      const res = await authFetch(`${API_BASE}/properties/${property.id}/rent-rules`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          lateFeeGraceDays: graceDays === "" ? null : Number(graceDays),
          lateFeeAmount: feeAmount === "" ? null : Number(feeAmount),
          dueDay: dueDay === "" ? null : Number(dueDay),
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Couldn't save rent rules.");
      showToast(`Rent rules saved for ${property.name}`, "success");
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
      <div className="bg-white rounded-xl shadow-lg w-full max-w-md p-5">
        <div className="flex items-center justify-between mb-1">
          <h3 className="font-semibold">Rent rules — {property.name}</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600">
            <X size={18} />
          </button>
        </div>
        <p className="text-xs text-slate-500 mb-4">
          These directly drive the automated late-fee check — no manual step needed once set.
        </p>
        <div className="space-y-3">
          <div>
            <label htmlFor={`${idPrefix}-grace`} className="text-xs text-slate-500">
              Grace period (days after due date before a late fee applies)
            </label>
            <input
              id={`${idPrefix}-grace`}
              type="number"
              min="0"
              max="60"
              value={graceDays}
              onChange={(e) => setGraceDays(e.target.value)}
              placeholder="Default: 5"
              className="w-full text-sm border border-slate-200 rounded px-2 py-1.5 mt-0.5"
            />
          </div>
          <div>
            <label htmlFor={`${idPrefix}-fee`} className="text-xs text-slate-500">Late fee amount ($)</label>
            <input
              id={`${idPrefix}-fee`}
              type="number"
              min="0"
              value={feeAmount}
              onChange={(e) => setFeeAmount(e.target.value)}
              placeholder="Default: $50"
              className="w-full text-sm border border-slate-200 rounded px-2 py-1.5 mt-0.5"
            />
          </div>
          <div>
            <label htmlFor={`${idPrefix}-dueday`} className="text-xs text-slate-500">
              Rent due day of month (1–28)
            </label>
            <input
              id={`${idPrefix}-dueday`}
              type="number"
              min="1"
              max="28"
              value={dueDay}
              onChange={(e) => setDueDay(e.target.value)}
              placeholder="Not yet used by automation"
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
          {saving ? "Saving…" : "Save rent rules"}
        </button>
      </div>
    </div>
  );
}

function LeasingInfoModal({ property, onClose, onSaved }) {
  const [petPolicy, setPetPolicy] = useState(property.petPolicy ?? "");
  const [parkingInfo, setParkingInfo] = useState(property.parkingInfo ?? "");
  const [utilitiesIncluded, setUtilitiesIncluded] = useState(property.utilitiesIncluded ?? "");
  const [address, setAddress] = useState(property.address ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const { authFetch } = useAuth();
  const { show: showToast } = useToast();
  const idPrefix = useId();

  // Sends the raw current field values, including empty strings when
  // a field's been deliberately cleared - the backend's PATCH filters
  // out only None, not "", so an empty string here genuinely clears a
  // previously-set value (and the prospect-chat context gathering
  // already treats an empty string the same as "not set" via its own
  // falsy check) - sending null instead would have silently left the
  // old value in place, since this endpoint's PATCH semantics treat
  // omitted/null fields as "leave unchanged," not "clear."
  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      const res = await authFetch(`${API_BASE}/properties/${property.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ address, petPolicy, parkingInfo, utilitiesIncluded }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Couldn't save leasing info.");
      showToast(`Leasing info saved for ${property.name}`, "success");
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
      <div className="bg-white rounded-xl shadow-lg w-full max-w-md p-5">
        <div className="flex items-center justify-between mb-1">
          <h3 className="font-semibold">Leasing info — {property.name}</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600">
            <X size={18} />
          </button>
        </div>
        <p className="text-xs text-slate-500 mb-4">
          Answers the questions prospects actually ask on the public /apply chat — leave any field blank and the assistant will honestly say it doesn't know, rather than guess.
        </p>
        <div className="space-y-3">
          <div>
            <label htmlFor={`${idPrefix}-address`} className="text-xs text-slate-500">Address</label>
            <input
              id={`${idPrefix}-address`}
              value={address}
              onChange={(e) => setAddress(e.target.value)}
              className="w-full text-sm border border-slate-200 rounded px-2 py-1.5 mt-0.5"
            />
          </div>
          <div>
            <label htmlFor={`${idPrefix}-pets`} className="text-xs text-slate-500">Pet policy</label>
            <textarea
              id={`${idPrefix}-pets`}
              value={petPolicy}
              onChange={(e) => setPetPolicy(e.target.value)}
              rows={2}
              placeholder="e.g. Cats and dogs under 40lbs welcome, $300 deposit"
              className="w-full text-sm border border-slate-200 rounded px-2 py-1.5 mt-0.5"
            />
          </div>
          <div>
            <label htmlFor={`${idPrefix}-parking`} className="text-xs text-slate-500">Parking</label>
            <textarea
              id={`${idPrefix}-parking`}
              value={parkingInfo}
              onChange={(e) => setParkingInfo(e.target.value)}
              rows={2}
              placeholder="e.g. 1 assigned spot per unit, street parking also available"
              className="w-full text-sm border border-slate-200 rounded px-2 py-1.5 mt-0.5"
            />
          </div>
          <div>
            <label htmlFor={`${idPrefix}-utilities`} className="text-xs text-slate-500">Utilities included</label>
            <textarea
              id={`${idPrefix}-utilities`}
              value={utilitiesIncluded}
              onChange={(e) => setUtilitiesIncluded(e.target.value)}
              rows={2}
              placeholder="e.g. Water and trash included, tenant pays electric/gas"
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
          {saving ? "Saving…" : "Save leasing info"}
        </button>
      </div>
    </div>
  );
}

function TelephonyModal({ property, onClose, onSaved }) {
  const [twilioNumber, setTwilioNumber] = useState(property.twilioNumber ?? "");
  const [afterHoursStart, setAfterHoursStart] = useState(property.afterHoursStart ?? "");
  const [afterHoursEnd, setAfterHoursEnd] = useState(property.afterHoursEnd ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const { authFetch } = useAuth();
  const { show: showToast } = useToast();
  const idPrefix = useId();

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      const res = await authFetch(`${API_BASE}/properties/${property.id}/telephony`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          twilioNumber: twilioNumber.trim() === "" ? null : twilioNumber.trim(),
          afterHoursStart: afterHoursStart === "" ? null : afterHoursStart,
          afterHoursEnd: afterHoursEnd === "" ? null : afterHoursEnd,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Couldn't save telephony settings.");
      showToast(`Telephony settings saved for ${property.name}`, "success");
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
      <div className="bg-white rounded-xl shadow-lg w-full max-w-md p-5">
        <div className="flex items-center justify-between mb-1">
          <h3 className="font-semibold">Telephony — {property.name}</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600">
            <X size={18} />
          </button>
        </div>
        <p className="text-xs text-slate-500 mb-4">
          Set the Twilio number that routes after-hours maintenance calls for this
          building. Buy and configure the number itself in your Twilio console first
          (Voice webhook → <code className="bg-slate-100 px-1 rounded">https://rentflow-ai.onrender.com/api/telephony/voice</code>,
          method POST) — this just tells PropWise AI which number belongs to which
          property once that's done.
        </p>
        <div className="space-y-3">
          <div>
            <label htmlFor={`${idPrefix}-number`} className="text-xs text-slate-500">
              Twilio phone number
            </label>
            <input
              id={`${idPrefix}-number`}
              type="tel"
              value={twilioNumber}
              onChange={(e) => setTwilioNumber(e.target.value)}
              placeholder="+17372324091"
              className="w-full text-sm border border-slate-200 rounded px-2 py-1.5 mt-0.5"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label htmlFor={`${idPrefix}-start`} className="text-xs text-slate-500">
                After-hours start
              </label>
              <input
                id={`${idPrefix}-start`}
                type="time"
                value={afterHoursStart}
                onChange={(e) => setAfterHoursStart(e.target.value)}
                className="w-full text-sm border border-slate-200 rounded px-2 py-1.5 mt-0.5"
              />
            </div>
            <div>
              <label htmlFor={`${idPrefix}-end`} className="text-xs text-slate-500">
                After-hours end
              </label>
              <input
                id={`${idPrefix}-end`}
                type="time"
                value={afterHoursEnd}
                onChange={(e) => setAfterHoursEnd(e.target.value)}
                className="w-full text-sm border border-slate-200 rounded px-2 py-1.5 mt-0.5"
              />
            </div>
          </div>
          <p className="text-[11px] text-slate-400">
            Leave both times blank to treat every hour as after-hours (routes calls to
            on-call staff around the clock).
          </p>
        </div>
        {error && <p role="alert" className="text-xs text-rose-600 mt-3 bg-rose-50 border border-rose-200 rounded px-3 py-2">{error}</p>}
        <button
          onClick={handleSave}
          disabled={saving}
          className="mt-4 w-full bg-slate-900 disabled:bg-slate-300 text-white text-sm font-semibold py-2.5 rounded-lg hover:bg-slate-800"
        >
          {saving ? "Saving…" : "Save telephony settings"}
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
  const [rentRulesFor, setRentRulesFor] = useState(null); // property | null
  const [leasingInfoFor, setLeasingInfoFor] = useState(null); // property | null
  const [telephonyFor, setTelephonyFor] = useState(null); // property | null
  const [search, setSearch] = useState("");
  const { authFetch } = useAuth();
  // Real status filter, driven by a real URL query param
  // (?status=vacant|occupied|maintenance_hold) - this is what makes
  // the Dashboard's occupancy chart segments genuinely clickable
  // links rather than static visuals: clicking "Vacant" navigates
  // here with ?status=vacant already in the URL, and this page reads
  // it directly rather than requiring a second manual filter step.
  const [searchParams, setSearchParams] = useSearchParams();
  const statusFilter = searchParams.get("status");

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

  // Matches by property name (partial — "Sunset" should find "Sunset
  // Apartments") OR unit number (exact — a partial/substring match on
  // unit numbers caused real confusion: searching "105" was also
  // matching "1105", which is a genuinely different unit, not a
  // reasonable partial match the way it is for names).
  const filteredProperties = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return properties;
    return properties
      .map((p) => {
        const nameMatches = p.name.toLowerCase().includes(q);
        if (nameMatches) return p;
        const matchingUnits = (p.units || []).filter((u) => u.unitId.toLowerCase() === q);
        return matchingUnits.length > 0 ? { ...p, units: matchingUnits } : null;
      })
      .filter(Boolean);
  }, [properties, search]);

  return (
    <div className="max-w-2xl mx-auto">
      {statusFilter && (
        <div className="flex items-center justify-between bg-indigo-50 border border-indigo-100 rounded-lg px-3 py-2 mb-3 text-sm">
          <span className="text-indigo-700">
            Showing only <strong>{statusFilter.replace("_", " ")}</strong> units
          </span>
          <button
            onClick={() => setSearchParams({})}
            className="text-indigo-600 underline text-xs font-medium"
          >
            Clear filter
          </button>
        </div>
      )}
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

      {!loading && !error && properties.length > 0 && (
        <div className="relative mb-3">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by property name or unit number…"
            className="w-full text-sm border border-slate-200 rounded-lg pl-9 pr-3 py-2"
          />
        </div>
      )}

      {loading ? (
        <div className="h-40 bg-slate-100 rounded-xl animate-pulse" />
      ) : error ? (
        <p role="alert" aria-live="polite" className="text-sm text-rose-600 bg-rose-50 border border-rose-200 rounded-xl px-4 py-3">{error}</p>
      ) : properties.length === 0 ? (
        <p className="text-sm text-slate-400 flex items-center gap-2"><Building2 size={16} /> No properties yet.</p>
      ) : filteredProperties.length === 0 ? (
        <p className="text-sm text-slate-400">No properties or units match "{search}".</p>
      ) : (
        <div className="space-y-3">
          {filteredProperties.map((p) => (
            <div key={p.id} className="bg-white border border-slate-200 rounded-xl p-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-semibold">{p.name}</span>
                <div className="flex items-center gap-3">
                  <button
                    onClick={() => setRentRulesFor(p)}
                    className="flex items-center gap-1 text-[11px] text-indigo-700 hover:underline"
                  >
                    <Settings2 size={12} />
                    Rent rules
                  </button>
                  <button
                    onClick={() => setLeasingInfoFor(p)}
                    className="flex items-center gap-1 text-[11px] text-indigo-700 hover:underline"
                  >
                    <Pencil size={12} />
                    Leasing info
                  </button>
                  <button
                    onClick={() => setTelephonyFor(p)}
                    className="flex items-center gap-1 text-[11px] text-indigo-700 hover:underline"
                  >
                    <Phone size={12} />
                    Telephony
                  </button>
                  <button
                    onClick={() => setAddUnitTo(p)}
                    className="flex items-center gap-1 text-[11px] text-indigo-700 hover:underline"
                  >
                    <Plus size={12} />
                    Add unit
                  </button>
                </div>
              </div>
              <p className="text-[11px] text-slate-400 mb-2">
                {p.lateFeeGraceDays != null || p.lateFeeAmount != null ? (
                  <>Grace: {p.lateFeeGraceDays ?? 5}d · Late fee: ${p.lateFeeAmount ?? 50}</>
                ) : (
                  <span className="text-amber-600">Using default rent rules — not yet configured for this building</span>
                )}
              </p>
              <div className="flex flex-wrap gap-1.5">
                {(p.units || [])
                  .filter((u) => !statusFilter || u.status === statusFilter)
                  .map((u) => {
                    // Same real 3-status color scheme as the Dashboard's
                    // occupancy chart (OCCUPANCY_COLORS in Dashboard.jsx) -
                    // a unit's status reads the same way wherever it's shown.
                    const statusStyle = {
                      occupied: "bg-indigo-50 text-indigo-700 border-indigo-200",
                      vacant: "bg-slate-50 text-slate-600 border-slate-200",
                      maintenance_hold: "bg-amber-50 text-amber-700 border-amber-200",
                    }[u.status] || "bg-slate-50 text-slate-600 border-slate-200";
                    return (
                      <button
                        key={u.unitId}
                        onClick={() => setEditingUnit({ property: p, unit: u })}
                        className={`flex items-center gap-1 text-[11px] px-2 py-1 rounded-full border hover:border-indigo-300 ${statusStyle}`}
                        title={`${u.status?.replace("_", " ") || "unknown"} — click to edit rent/bed/bath`}
                      >
                        {u.unitId}
                        <Pencil size={9} />
                      </button>
                    );
                  })}
                {statusFilter && (p.units || []).every((u) => u.status !== statusFilter) && (
                  <span className="text-[11px] text-slate-400 italic">No {statusFilter.replace("_", " ")} units here</span>
                )}
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
      {rentRulesFor && (
        <RentRulesModal
          property={rentRulesFor}
          onClose={() => setRentRulesFor(null)}
          onSaved={fetchProperties}
        />
      )}
      {leasingInfoFor && (
        <LeasingInfoModal
          property={leasingInfoFor}
          onClose={() => setLeasingInfoFor(null)}
          onSaved={fetchProperties}
        />
      )}
      {telephonyFor && (
        <TelephonyModal
          property={telephonyFor}
          onClose={() => setTelephonyFor(null)}
          onSaved={fetchProperties}
        />
      )}
    </div>
  );
}
