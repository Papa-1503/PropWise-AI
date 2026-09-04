import { useState, useEffect, useCallback } from "react";
import { useParams } from "react-router-dom";
import { API_BASE } from "./config";
import { Camera, CheckCircle2 } from "lucide-react";

/**
 * PhotoUploadPage — the public /upload-photos/:token page.
 *
 * No login required, same principle as /apply and vendor_acceptance's
 * tokenized links - a resident who reported an issue by phone or text
 * doesn't necessarily have (or want to create) an app account just to
 * send a photo. The unguessable token itself is what gates access;
 * see backend/routers/photo_upload.py for the real reasoning.
 */
export default function PhotoUploadPage() {
  const { token } = useParams();
  const [context, setContext] = useState(null); // { ticketTitle, propertyName, unitId, photoCount } | "invalid"
  const [uploading, setUploading] = useState(false);
  const [uploadedCount, setUploadedCount] = useState(0);
  const [error, setError] = useState(null);

  const fetchContext = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/photo-upload/${token}`);
      if (!res.ok) {
        setContext("invalid");
        return;
      }
      const data = await res.json();
      setContext(data);
      setUploadedCount(data.photoCount || 0);
    } catch {
      setContext("invalid");
    }
  }, [token]);

  useEffect(() => {
    fetchContext();
  }, [fetchContext]);

  async function handleFiles(e) {
    const files = Array.from(e.target.files || []);
    if (files.length === 0) return;
    setUploading(true);
    setError(null);
    let succeeded = 0;
    for (const file of files) {
      try {
        const formData = new FormData();
        formData.append("file", file);
        const res = await fetch(`${API_BASE}/photo-upload/${token}`, { method: "POST", body: formData });
        if (res.ok) succeeded++;
      } catch {
        // one photo failing shouldn't stop the rest from trying
      }
    }
    if (succeeded > 0) setUploadedCount((c) => c + succeeded);
    if (succeeded < files.length) setError(`${files.length - succeeded} photo(s) didn't upload — you can try again.`);
    setUploading(false);
    e.target.value = "";
  }

  if (context === null) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50 p-4">
        <p className="text-sm text-slate-400">Loading…</p>
      </div>
    );
  }

  if (context === "invalid") {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50 p-4">
        <div className="bg-white border border-slate-200 rounded-xl p-6 max-w-sm text-center">
          <h1 className="text-lg font-semibold mb-2">Link expired</h1>
          <p className="text-sm text-slate-500">
            This photo-upload link is invalid or has expired. Please contact the property office if you still
            need to send a photo.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 p-4">
      <div className="bg-white border border-slate-200 rounded-xl p-6 max-w-sm w-full">
        <h1 className="text-lg font-semibold mb-1">Add a photo</h1>
        <p className="text-sm text-slate-500 mb-4">
          {context.ticketTitle}
          {context.propertyName && <> · {context.propertyName}</>}
          {context.unitId && <> · Unit {context.unitId}</>}
        </p>

        {uploadedCount > 0 && (
          <div className="flex items-center gap-2 text-sm text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-2 mb-3">
            <CheckCircle2 size={16} />
            {uploadedCount} photo{uploadedCount !== 1 ? "s" : ""} sent — thank you.
          </div>
        )}

        {error && (
          <p className="text-xs text-rose-600 bg-rose-50 border border-rose-200 rounded px-3 py-2 mb-3">{error}</p>
        )}

        <label className="flex flex-col items-center justify-center gap-2 text-sm font-medium text-indigo-600 border-2 border-dashed border-indigo-200 rounded-xl py-8 cursor-pointer hover:bg-indigo-50">
          <Camera size={22} />
          {uploading ? "Uploading…" : "Take or choose a photo"}
          <input
            type="file"
            accept="image/*"
            multiple
            capture="environment"
            className="hidden"
            onChange={handleFiles}
            disabled={uploading}
          />
        </label>
        <p className="text-[11px] text-slate-400 mt-3 text-center">
          You can send more than one photo, and close this page whenever you're done.
        </p>
      </div>
    </div>
  );
}
