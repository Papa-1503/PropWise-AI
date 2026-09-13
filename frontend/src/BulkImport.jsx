import { useState, useRef } from "react";
import { Upload, Download, CheckCircle2, AlertTriangle, Building2, FileSignature, Link2, Eye } from "lucide-react";
import { useAuth } from "./AuthContext";
import { useToast } from "./ToastContext";
import { API_BASE } from "./config";

/**
 * BulkImport
 *
 * The real, missing onboarding fast-path (backend: routers/bulk_import.py) -
 * before this, a new organization with an existing portfolio had no way
 * to get their properties/units/leases into PropWise AI except re-typing
 * every one by hand through the UI. Two independent imports, matching the
 * backend's own two endpoints: properties/units first (creates the
 * physical structure), then leases (fills units with residents) - a
 * lease import will cleanly fail row-by-row if it references a property/
 * unit that doesn't exist yet, so running them in this order matters.
 *
 * Both imports are idempotent on the backend - safe to fix a few bad
 * rows in a spreadsheet and re-upload the same file without creating
 * duplicates. Results always show real counts plus every row-level
 * error with its original row number, never a silent partial success.
 *
 * CHANGED Sept 13, 2026: added a third, direct import path - a real
 * Buildium integration (backend: routers/buildium_import.py), for a
 * customer migrating from Buildium specifically, whose Open API is
 * genuinely self-serve (a customer generates their own API key
 * directly from their own Buildium account). Other major platforms
 * like AppFolio require PropWise AI itself to become an approved
 * partner first - a business step, not something this UI can offer
 * yet. Deliberately a real preview-before-commit flow: Buildium's
 * exact field names couldn't be fully verified against a live
 * customer account during development, so staff see the real fetched
 * data (property names, rents, resident names) before anything is
 * written, rather than trusting a field-mapping guess blindly.
 */

function downloadBlob(blob, filename) {
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
}

function ImportCard({ icon: Icon, title, description, templateUrl, templateFilename, uploadUrl, resultLabels }) {
  const { authFetch } = useAuth();
  const { show: showToast } = useToast();
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const fileInputRef = useRef(null);

  async function handleDownloadTemplate() {
    try {
      const res = await authFetch(`${API_BASE}${templateUrl}`);
      if (!res.ok) throw new Error("Couldn't download the template.");
      const blob = await res.blob();
      downloadBlob(blob, templateFilename);
    } catch (err) {
      showToast(err.message, "error");
    }
  }

  async function handleFileChosen(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setError(null);
    setResult(null);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await authFetch(`${API_BASE}${uploadUrl}`, { method: "POST", body: formData });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Import failed.");
      setResult(data);
      if (data.errors?.length === 0) {
        showToast("Import completed with no errors.", "success");
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5 space-y-4">
      <div className="flex items-start gap-3">
        <div className="w-9 h-9 rounded-lg bg-indigo-50 flex items-center justify-center shrink-0">
          <Icon size={18} className="text-indigo-600" />
        </div>
        <div>
          <h3 className="text-sm font-semibold">{title}</h3>
          <p className="text-xs text-slate-500 mt-0.5">{description}</p>
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        <button
          onClick={handleDownloadTemplate}
          className="flex items-center gap-1.5 text-xs font-semibold text-indigo-700 border border-indigo-200 bg-indigo-50 hover:bg-indigo-100 px-3 py-2 rounded-lg"
        >
          <Download size={14} />
          Download CSV template
        </button>
        <label className="flex items-center gap-1.5 text-xs font-semibold text-white bg-slate-900 hover:bg-slate-800 px-3 py-2 rounded-lg cursor-pointer">
          <Upload size={14} />
          {uploading ? "Importing…" : "Upload CSV"}
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv"
            onChange={handleFileChosen}
            disabled={uploading}
            className="hidden"
          />
        </label>
      </div>

      {error && (
        <p role="alert" className="text-xs text-rose-600 bg-rose-50 border border-rose-200 rounded px-3 py-2">
          {error}
        </p>
      )}

      {result && (
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-xs font-semibold text-emerald-700">
            <CheckCircle2 size={15} />
            {resultLabels(result)}
          </div>
          {result.errors?.length > 0 && (
            <div className="bg-amber-50 border border-amber-200 rounded-lg p-3">
              <div className="flex items-center gap-1.5 text-xs font-semibold text-amber-800 mb-1.5">
                <AlertTriangle size={13} />
                {result.errors.length} row{result.errors.length === 1 ? "" : "s"} need attention
              </div>
              <ul className="space-y-1 max-h-48 overflow-y-auto">
                {result.errors.map((e, i) => (
                  <li key={i} className="text-[11px] text-amber-800 leading-relaxed">{e}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function BuildiumImportCard() {
  const { authFetch } = useAuth();
  const { show: showToast } = useToast();
  const [clientId, setClientId] = useState("");
  const [clientSecret, setClientSecret] = useState("");
  const [previewing, setPreviewing] = useState(false);
  const [committing, setCommitting] = useState(false);
  const [preview, setPreview] = useState(null);
  const [committed, setCommitted] = useState(null);
  const [error, setError] = useState(null);

  async function handlePreview() {
    if (!clientId.trim() || !clientSecret.trim()) {
      setError("Enter both the Client ID and Secret from Buildium's Settings > Developer Tools.");
      return;
    }
    setPreviewing(true);
    setError(null);
    setPreview(null);
    setCommitted(null);
    try {
      const res = await authFetch(`${API_BASE}/import/buildium/preview`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ clientId: clientId.trim(), clientSecret: clientSecret.trim() }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Couldn't connect to Buildium.");
      setPreview(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setPreviewing(false);
    }
  }

  async function handleCommit() {
    setCommitting(true);
    setError(null);
    try {
      const res = await authFetch(`${API_BASE}/import/buildium/commit`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ clientId: clientId.trim(), clientSecret: clientSecret.trim() }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Import failed.");
      setCommitted(data);
      showToast("Buildium import complete.", "success");
    } catch (err) {
      setError(err.message);
    } finally {
      setCommitting(false);
    }
  }

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5 space-y-4">
      <div className="flex items-start gap-3">
        <div className="w-9 h-9 rounded-lg bg-indigo-50 flex items-center justify-center shrink-0">
          <Link2 size={18} className="text-indigo-600" />
        </div>
        <div>
          <h3 className="text-sm font-semibold">Import directly from Buildium</h3>
          <p className="text-xs text-slate-500 mt-0.5">
            Migrating from Buildium? Connect with your own Buildium API key to pull your properties,
            units, and leases automatically — no spreadsheet needed. Generate a key in Buildium under
            Settings → Developer Tools. Your credentials are used only for this import and are never stored.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        <div>
          <label className="text-xs text-slate-500">Buildium Client ID</label>
          <input
            value={clientId}
            onChange={(e) => setClientId(e.target.value)}
            className="w-full text-sm border border-slate-200 rounded px-2 py-1.5 mt-0.5 font-mono"
          />
        </div>
        <div>
          <label className="text-xs text-slate-500">Buildium Client Secret</label>
          <input
            type="password"
            value={clientSecret}
            onChange={(e) => setClientSecret(e.target.value)}
            className="w-full text-sm border border-slate-200 rounded px-2 py-1.5 mt-0.5 font-mono"
          />
        </div>
      </div>

      {error && (
        <p role="alert" className="text-xs text-rose-600 bg-rose-50 border border-rose-200 rounded px-3 py-2">
          {error}
        </p>
      )}

      {!committed && (
        <button
          onClick={handlePreview}
          disabled={previewing}
          className="flex items-center gap-1.5 text-xs font-semibold text-white bg-slate-900 hover:bg-slate-800 disabled:bg-slate-300 px-3 py-2 rounded-lg"
        >
          <Eye size={14} />
          {previewing ? "Connecting to Buildium…" : "Preview what will be imported"}
        </button>
      )}

      {preview && !committed && (
        <div className="space-y-3">
          <div className="bg-indigo-50 border border-indigo-200 rounded-lg p-3">
            <p className="text-xs font-semibold text-indigo-800 mb-1">
              Found {preview.propertyCount} propert{preview.propertyCount === 1 ? "y" : "ies"},{" "}
              {preview.unitCount} unit{preview.unitCount === 1 ? "" : "s"}, {preview.leaseCount} lease
              {preview.leaseCount === 1 ? "" : "s"} in Buildium.
            </p>
            {preview.sampleProperties?.length > 0 && (
              <p className="text-[11px] text-indigo-700">
                First property: {preview.sampleProperties[0].name}
                {preview.sampleProperties[0].address ? ` — ${preview.sampleProperties[0].address}` : ""}
              </p>
            )}
            {preview.sampleLeases?.length > 0 && (
              <p className="text-[11px] text-indigo-700">
                First lease: {preview.sampleLeases[0].residentName}, ${preview.sampleLeases[0].rent}/mo
              </p>
            )}
          </div>
          <p className="text-[11px] text-slate-500">
            Double-check the names, rents, and dates above look right — this is real data pulled directly
            from your Buildium account. Once you confirm, this will be imported into PropWise AI.
          </p>
          <button
            onClick={handleCommit}
            disabled={committing}
            className="flex items-center gap-1.5 text-xs font-semibold text-white bg-emerald-600 hover:bg-emerald-700 disabled:bg-emerald-300 px-3 py-2 rounded-lg"
          >
            <CheckCircle2 size={14} />
            {committing ? "Importing…" : "This looks right — import it"}
          </button>
        </div>
      )}

      {committed && (
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-xs font-semibold text-emerald-700">
            <CheckCircle2 size={15} />
            {committed.propertiesCreated} propert{committed.propertiesCreated === 1 ? "y" : "ies"} created,{" "}
            {committed.propertiesUpdated} updated, {committed.unitsAdded} unit{committed.unitsAdded === 1 ? "" : "s"} added,{" "}
            {committed.leasesCreated} lease{committed.leasesCreated === 1 ? "" : "s"} created
          </div>
          {committed.leaseErrors?.length > 0 && (
            <div className="bg-amber-50 border border-amber-200 rounded-lg p-3">
              <div className="flex items-center gap-1.5 text-xs font-semibold text-amber-800 mb-1.5">
                <AlertTriangle size={13} />
                {committed.leaseErrors.length} lease{committed.leaseErrors.length === 1 ? "" : "s"} skipped
              </div>
              <ul className="space-y-1">
                {committed.leaseErrors.map((e, i) => (
                  <li key={i} className="text-[11px] text-amber-800 leading-relaxed">{e}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function BulkImport() {
  return (
    <div className="max-w-2xl space-y-5">
      <div>
        <h2 className="text-lg font-semibold">Import Data</h2>
        <p className="text-sm text-slate-500 mt-1">
          Bringing over an existing portfolio? Import your properties and leases from a spreadsheet,
          or connect directly to Buildium below. If importing by spreadsheet, import properties first,
          then leases — a lease import needs its property and unit to already exist.
        </p>
      </div>

      <BuildiumImportCard />

      <ImportCard
        icon={Building2}
        title="1. Import Properties & Units"
        description="One row per unit. Rows sharing the same property name become units under one property."
        templateUrl="/import/properties/template"
        templateFilename="propwise_properties_template.csv"
        uploadUrl="/import/properties"
        resultLabels={(r) => `${r.propertiesCreated} propert${r.propertiesCreated === 1 ? "y" : "ies"} created, ${r.propertiesUpdated} updated, ${r.unitsAdded} unit${r.unitsAdded === 1 ? "" : "s"} added`}
      />

      <ImportCard
        icon={FileSignature}
        title="2. Import Leases"
        description="One row per lease. property_name and unit_id must match a property/unit you've already added."
        templateUrl="/import/leases/template"
        templateFilename="propwise_leases_template.csv"
        uploadUrl="/import/leases"
        resultLabels={(r) => `${r.leasesCreated} lease${r.leasesCreated === 1 ? "" : "s"} created`}
      />
    </div>
  );
}
