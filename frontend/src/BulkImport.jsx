import { useState, useRef } from "react";
import { Upload, Download, CheckCircle2, AlertTriangle, Building2, FileSignature } from "lucide-react";
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

export default function BulkImport() {
  return (
    <div className="max-w-2xl space-y-5">
      <div>
        <h2 className="text-lg font-semibold">Import Data</h2>
        <p className="text-sm text-slate-500 mt-1">
          Bringing over an existing portfolio? Import your properties and leases from a spreadsheet
          instead of entering them one at a time. Import properties first, then leases — a lease
          import needs its property and unit to already exist.
        </p>
      </div>

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
