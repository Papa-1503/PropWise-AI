import { useState, useRef, useCallback } from "react";
import { useAuth } from "./AuthContext";

/**
 * InspectionChecklist
 *
 * Real inspection workflow component:
 * - Room-by-room checklist with pass/flag/fail states
 * - Photo upload with actual click-to-annotate (canvas-based, not decorative CSS)
 * - Submits to your FastAPI backend; auto-creates maintenance tickets for flagged items
 *
 * Assumptions (adjust to match your actual backend):
 *   POST /api/inspections                -> create/save an inspection record
 *   POST /api/inspections/:id/photos     -> upload a photo (multipart/form-data)
 *   POST /api/maintenance/tickets        -> auto-create a ticket from a flagged item
 *
 * Expected inspection record shape sent to the API:
 * {
 *   propertyId, unitId, inspectorName, type: "move-in"|"move-out"|"annual",
 *   items: [{ room, description, status: "pass"|"flag"|"fail", photoIds: [] }]
 * }
 */

import { API_BASE } from "./config";

const STATUS_STYLES = {
  pass: "bg-emerald-50 text-emerald-700 border-emerald-200",
  flag: "bg-amber-50 text-amber-700 border-amber-200",
  fail: "bg-rose-50 text-rose-700 border-rose-200",
  pending: "bg-slate-50 text-slate-500 border-slate-200",
};

function StatusPill({ status }) {
  return (
    <span
      className={`inline-block px-2.5 py-0.5 rounded-full text-[11px] font-mono uppercase tracking-wide border ${STATUS_STYLES[status] || STATUS_STYLES.pending}`}
    >
      {status}
    </span>
  );
}

/** A single photo with click-to-mark annotation drawn on a real canvas,
 *  plus optional AI-assisted visual recognition of visible issues. */
function AnnotatablePhoto({ photo, room, onAddMark, onRemove, onApplyAISummary, authFetch }) {
  const canvasRef = useRef(null);
  const imgRef = useRef(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [aiResult, setAiResult] = useState(null);
  const [aiError, setAiError] = useState(null);

  async function handleAnalyze() {
    setAnalyzing(true);
    setAiError(null);
    try {
      const form = new FormData();
      form.append("file", photo.file);
      form.append("room", room);
      const res = await authFetch(`${API_BASE}/inspections/analyze-photo`, {
        method: "POST",
        body: form,
      });
      if (!res.ok) throw new Error(`Server returned ${res.status}`);
      const data = await res.json();
      setAiResult(data);
    } catch (err) {
      setAiError("AI analysis failed — describe the issue manually.");
    } finally {
      setAnalyzing(false);
    }
  }

  const drawMarks = useCallback(() => {
    const canvas = canvasRef.current;
    const img = imgRef.current;
    if (!canvas || !img) return;
    const ctx = canvas.getContext("2d");
    canvas.width = img.clientWidth;
    canvas.height = img.clientHeight;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    photo.marks.forEach((m) => {
      ctx.beginPath();
      ctx.arc(m.x, m.y, 10, 0, Math.PI * 2);
      ctx.strokeStyle = "#b5462f";
      ctx.lineWidth = 2.5;
      ctx.stroke();
    });
  }, [photo.marks]);

  const handleClick = (e) => {
    const rect = canvasRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    onAddMark(photo.id, { x, y });
  };

  const severityStyle = {
    low: "bg-slate-100 text-slate-600",
    medium: "bg-amber-100 text-amber-700",
    high: "bg-rose-100 text-rose-700",
  };

  return (
    <div className="w-32">
      <div className="relative w-32 h-24 rounded-md overflow-hidden border border-slate-200 group">
        <img
          ref={imgRef}
          src={photo.url}
          alt={photo.name}
          className="w-full h-full object-cover"
          onLoad={drawMarks}
        />
        <canvas
          ref={canvasRef}
          onClick={handleClick}
          className="absolute inset-0 cursor-crosshair"
          title="Click to mark a damage point"
        />
        <button
          onClick={() => onRemove(photo.id)}
          className="absolute top-1 right-1 bg-black/60 text-white text-[10px] rounded px-1 opacity-0 group-hover:opacity-100"
        >
          ✕
        </button>
        <span className="absolute bottom-0 left-0 right-0 bg-black/60 text-white text-[9px] font-mono px-1 truncate">
          {photo.name} · {photo.marks.length} mark{photo.marks.length !== 1 ? "s" : ""}
        </span>
      </div>

      <button
        onClick={handleAnalyze}
        disabled={analyzing}
        className="w-full mt-1 text-[10px] font-mono bg-indigo-50 text-indigo-700 border border-indigo-200 rounded px-1.5 py-1 hover:bg-indigo-100 disabled:opacity-50"
      >
        {analyzing ? "Analyzing…" : "🔍 Analyze with AI"}
      </button>

      {aiError && <p className="text-[9px] text-rose-500 mt-1">{aiError}</p>}

      {aiResult && (
        <div className="mt-1.5 w-56 bg-white border border-indigo-200 rounded-lg p-2.5 text-[11px] shadow-sm">
          <p className="text-slate-700">{aiResult.summary}</p>
          {aiResult.issues.length > 0 ? (
            <ul className="mt-1.5 space-y-1">
              {aiResult.issues.map((issue, i) => (
                <li key={i} className="flex items-start gap-1.5">
                  <span className={`text-[9px] font-mono uppercase px-1 rounded ${severityStyle[issue.severity]}`}>
                    {issue.severity}
                  </span>
                  <span>
                    <b>{issue.label}</b> — {issue.description}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-[10px] text-slate-400 italic mt-1">No visible issues detected.</p>
          )}
          {aiResult.issues.length > 0 && (
            <button
              onClick={() => onApplyAISummary(aiResult)}
              className="text-[10px] font-semibold text-indigo-700 underline mt-1.5"
            >
              Use as description
            </button>
          )}
          <p className="text-[9px] text-slate-400 italic mt-1.5">
            AI-suggested — review before relying on it.
          </p>
        </div>
      )}
    </div>
  );
}

function ChecklistRow({ item, onChangeStatus, onChangeDesc, onPhotoUpload, onAddMark, onRemovePhoto, authFetch }) {
  const fileInputRef = useRef(null);

  function handleApplyAISummary(aiResult) {
    const issueText = aiResult.issues.map((i) => `${i.label}: ${i.description}`).join("; ");
    const combined = item.description ? `${item.description} — ${issueText}` : issueText;
    onChangeDesc(item.id, combined);
    // an AI-detected medium/high issue is a reasonable default nudge toward "flag",
    // but the inspector can always override it
    const worstSeverity = aiResult.issues.some((i) => i.severity === "high")
      ? "fail"
      : aiResult.issues.some((i) => i.severity === "medium")
      ? "flag"
      : item.status;
    if (worstSeverity !== item.status) onChangeStatus(item.id, worstSeverity);
  }

  return (
    <div className="border-b border-slate-200 py-3 last:border-none">
      <div className="flex items-start gap-3">
        <span className="font-mono text-[12px] text-slate-500 min-w-[100px] pt-1">{item.room}</span>
        <input
          value={item.description}
          onChange={(e) => onChangeDesc(item.id, e.target.value)}
          placeholder="Describe condition or issue..."
          className="flex-1 text-sm border border-slate-200 rounded px-2 py-1.5"
        />
        <div className="flex gap-1">
          {["pass", "flag", "fail"].map((s) => (
            <button
              key={s}
              onClick={() => onChangeStatus(item.id, s)}
              className={`px-2 py-1 rounded text-[11px] font-mono uppercase border ${
                item.status === s ? STATUS_STYLES[s] : "border-slate-200 text-slate-400"
              }`}
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      {(item.status === "flag" || item.status === "fail") && (
        <div className="mt-2 pl-[112px] flex flex-wrap gap-2 items-center">
          {item.photos.map((p) => (
            <AnnotatablePhoto
              key={p.id}
              photo={p}
              room={item.room}
              authFetch={authFetch}
              onAddMark={(photoId, mark) => onAddMark(item.id, photoId, mark)}
              onRemove={(photoId) => onRemovePhoto(item.id, photoId)}
              onApplyAISummary={handleApplyAISummary}
            />
          ))}
          <button
            onClick={() => fileInputRef.current?.click()}
            className="w-32 h-24 border-2 border-dashed border-slate-300 rounded-md text-slate-400 text-xs hover:border-amber-400 hover:text-amber-600"
          >
            + Add photo
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            multiple
            className="hidden"
            onChange={(e) => onPhotoUpload(item.id, e.target.files)}
          />
        </div>
      )}
    </div>
  );
}

export default function InspectionChecklist({
  propertyId,
  unitId,
  inspectorName = "",
  inspectionType = "annual",
}) {
  const [items, setItems] = useState([
    { id: crypto.randomUUID(), room: "Kitchen", description: "", status: "pending", photos: [] },
    { id: crypto.randomUUID(), room: "Bathroom", description: "", status: "pending", photos: [] },
    { id: crypto.randomUUID(), room: "Bedroom 1", description: "", status: "pending", photos: [] },
    { id: crypto.randomUUID(), room: "Living room", description: "", status: "pending", photos: [] },
  ]);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState(null);
  const [submitted, setSubmitted] = useState(false);
  const [submittedInspectionId, setSubmittedInspectionId] = useState(null);
  const [downloadingPdf, setDownloadingPdf] = useState(false);
  const { authFetch } = useAuth();

  const updateItem = (id, patch) =>
    setItems((prev) => prev.map((it) => (it.id === id ? { ...it, ...patch } : it)));

  const handleChangeStatus = (id, status) => updateItem(id, { status });
  const handleChangeDesc = (id, description) => updateItem(id, { description });

  const handlePhotoUpload = (itemId, fileList) => {
    const newPhotos = Array.from(fileList).map((file) => ({
      id: crypto.randomUUID(),
      file,
      url: URL.createObjectURL(file),
      name: file.name,
      marks: [],
    }));
    setItems((prev) =>
      prev.map((it) => (it.id === itemId ? { ...it, photos: [...it.photos, ...newPhotos] } : it))
    );
  };

  const handleAddMark = (itemId, photoId, mark) => {
    setItems((prev) =>
      prev.map((it) => {
        if (it.id !== itemId) return it;
        return {
          ...it,
          photos: it.photos.map((p) =>
            p.id === photoId ? { ...p, marks: [...p.marks, mark] } : p
          ),
        };
      })
    );
  };

  const handleRemovePhoto = (itemId, photoId) => {
    setItems((prev) =>
      prev.map((it) =>
        it.id === itemId ? { ...it, photos: it.photos.filter((p) => p.id !== photoId) } : it
      )
    );
  };

  const addRoom = () => {
    const room = window.prompt("Room name?");
    if (!room) return;
    setItems((prev) => [
      ...prev,
      { id: crypto.randomUUID(), room, description: "", status: "pending", photos: [] },
    ]);
  };

  /** Uploads any pending photo files for an item, returns array of server photo IDs. */
  async function uploadPhotosForItem(inspectionId, item) {
    const uploaded = [];
    for (const photo of item.photos) {
      const form = new FormData();
      form.append("file", photo.file);
      form.append("marks", JSON.stringify(photo.marks));
      form.append("room", item.room);
      const res = await authFetch(`${API_BASE}/inspections/${inspectionId}/photos`, {
        method: "POST",
        body: form,
      });
      if (!res.ok) throw new Error(`Photo upload failed for ${photo.name}`);
      const data = await res.json();
      uploaded.push(data.photoId);
    }
    return uploaded;
  }

  /** Auto-creates a maintenance ticket for any item flagged or failed. */
  async function autoCreateTickets(inspectionId, flaggedItems) {
    return Promise.all(
      flaggedItems.map((item) =>
        authFetch(`${API_BASE}/maintenance/tickets`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            propertyId,
            unitId,
            title: item.description || `${item.room} — flagged in inspection`,
            priority: item.status === "fail" ? "urgent" : "normal",
            sourceInspectionId: inspectionId,
            room: item.room,
          }),
        })
      )
    );
  }

  async function handleSubmit() {
    setSubmitting(true);
    setSubmitError(null);
    try {
      // 1. Create the inspection record
      const res = await authFetch(`${API_BASE}/inspections`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          propertyId,
          unitId,
          inspectorName,
          type: inspectionType,
          items: items.map(({ id, room, description, status }) => ({ id, room, description, status })),
        }),
      });
      if (!res.ok) throw new Error("Failed to save inspection");
      const { inspectionId } = await res.json();

      // 2. Upload photos for any flagged/failed items
      const flaggedItems = items.filter((it) => it.status === "flag" || it.status === "fail");
      for (const item of flaggedItems) {
        if (item.photos.length) await uploadPhotosForItem(inspectionId, item);
      }

      // 3. Auto-create maintenance tickets from flagged items
      if (flaggedItems.length) await autoCreateTickets(inspectionId, flaggedItems);

      setSubmitted(true);
      setSubmittedInspectionId(inspectionId);
    } catch (err) {
      setSubmitError(err.message || "Something went wrong submitting the inspection.");
    } finally {
      setSubmitting(false);
    }
  }

  const flaggedCount = items.filter((i) => i.status === "flag" || i.status === "fail").length;

  async function handleDownloadPdf() {
    if (!submittedInspectionId) return;
    setDownloadingPdf(true);
    try {
      const res = await authFetch(`${API_BASE}/inspections/${submittedInspectionId}/pdf`);
      if (!res.ok) throw new Error("Couldn't generate the report");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `inspection_${unitId}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch {
      alert("Couldn't download the PDF report — try again in a moment.");
    } finally {
      setDownloadingPdf(false);
    }
  }

  if (submitted) {
    return (
      <div className="max-w-2xl mx-auto p-6 text-center">
        <div className="text-2xl mb-2">✓</div>
        <h2 className="text-lg font-semibold">Inspection submitted</h2>
        <p className="text-sm text-slate-500 mt-1">
          {flaggedCount > 0
            ? `${flaggedCount} maintenance ticket${flaggedCount !== 1 ? "s were" : " was"} auto-created from flagged items.`
            : "No issues flagged — no maintenance tickets were needed."}
        </p>
        <button
          onClick={handleDownloadPdf}
          disabled={downloadingPdf}
          className="mt-4 text-sm font-semibold bg-slate-900 disabled:bg-slate-300 text-white px-4 py-2 rounded-lg"
        >
          {downloadingPdf ? "Generating…" : "Download PDF report"}
        </button>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto p-5 bg-white rounded-xl border border-slate-200">
      <div className="flex items-center justify-between mb-1">
        <h2 className="text-lg font-semibold">
          Unit {unitId} <span className="text-slate-400 font-normal">· {inspectionType} inspection</span>
        </h2>
        {flaggedCount > 0 && (
          <span className="text-xs font-mono text-amber-700 bg-amber-50 border border-amber-200 rounded-full px-2 py-0.5">
            {flaggedCount} flagged
          </span>
        )}
      </div>
      <p className="text-xs text-slate-500 mb-4">
        Click directly on a photo to mark a damage point. Flagged or failed items auto-generate maintenance tickets on submit.
      </p>

      <div>
        {items.map((item) => (
          <ChecklistRow
            key={item.id}
            item={item}
            onChangeStatus={handleChangeStatus}
            onChangeDesc={handleChangeDesc}
            onPhotoUpload={handlePhotoUpload}
            onAddMark={handleAddMark}
            onRemovePhoto={handleRemovePhoto}
            authFetch={authFetch}
          />
        ))}
      </div>

      <button onClick={addRoom} className="text-xs text-slate-500 mt-3 hover:text-amber-600">
        + Add room
      </button>

      {submitError && (
        <p className="text-xs text-rose-600 mt-3 bg-rose-50 border border-rose-200 rounded px-3 py-2">
          {submitError}
        </p>
      )}

      <button
        onClick={handleSubmit}
        disabled={submitting || items.some((i) => i.status === "pending")}
        className="mt-4 w-full bg-slate-900 disabled:bg-slate-300 text-white text-sm font-semibold py-2.5 rounded-lg hover:bg-slate-800"
      >
        {submitting ? "Submitting..." : "Submit inspection"}
      </button>
    </div>
  );
}
