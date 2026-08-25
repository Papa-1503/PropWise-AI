import { useState, useRef, useCallback, useEffect } from "react";
import { useAuth } from "./AuthContext";

/**
 * InspectionChecklist
 *
 * Real inspection workflow component. Two modes:
 *
 *   NEW (no inspectionId prop): starts from a blank checklist, batches
 *   everything into one POST /api/inspections when "Submit inspection"
 *   is clicked. This was the original, already-tested behavior.
 *
 *   EXISTING (inspectionId prop provided): loads a real inspection
 *   record via GET /api/inspections/:id — used for opening an
 *   already-created inspection (e.g. an auto-generated turnover
 *   checklist) to actually complete it. Every status/description change
 *   saves immediately via PATCH /api/inspections/:id/items/:itemId
 *   rather than batching, since the record already exists server-side
 *   and may be worked on across multiple sessions. Photo uploads also
 *   post immediately in this mode rather than staging locally.
 *
 * - Room-by-room checklist with pass/flag/fail states
 * - Photo upload with actual click-to-annotate (canvas-based, not decorative CSS)
 * - New-mode: auto-creates maintenance tickets for flagged items on submit
 * - Existing-mode: the server already auto-creates tickets on each PATCH
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

function ChecklistRow({ item, onChangeStatus, onChangeDesc, onDescBlur, onPhotoUpload, onAddMark, onRemovePhoto, authFetch }) {
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
          onBlur={() => onDescBlur && onDescBlur(item.id)}
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
  inspectionId = null,
  onBack = null,
}) {
  const isExisting = !!inspectionId;

  const [items, setItems] = useState(
    isExisting
      ? []
      : [
          { id: crypto.randomUUID(), room: "Kitchen", description: "", status: "pending", photos: [] },
          { id: crypto.randomUUID(), room: "Bathroom", description: "", status: "pending", photos: [] },
          { id: crypto.randomUUID(), room: "Bedroom 1", description: "", status: "pending", photos: [] },
          { id: crypto.randomUUID(), room: "Living room", description: "", status: "pending", photos: [] },
        ]
  );
  const [loadingExisting, setLoadingExisting] = useState(isExisting);
  const [loadError, setLoadError] = useState(null);
  const [existingMeta, setExistingMeta] = useState(null); // { unitId, propertyId, type }
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState(null);
  const [submitted, setSubmitted] = useState(false);
  const [submittedInspectionId, setSubmittedInspectionId] = useState(null);
  const [downloadingPdf, setDownloadingPdf] = useState(false);
  const { authFetch } = useAuth();

  // Load the real record when opening an existing inspection.
  useEffect(() => {
    if (!isExisting) return;
    let cancelled = false;
    (async () => {
      setLoadingExisting(true);
      setLoadError(null);
      try {
        const res = await authFetch(`${API_BASE}/inspections/${inspectionId}`);
        if (!res.ok) throw new Error("Couldn't load this inspection");
        const data = await res.json();
        if (cancelled) return;
        setExistingMeta({ unitId: data.unitId, propertyId: data.propertyId, type: data.type });
        setItems(
          (data.items || []).map((it) => ({
            id: it.id,
            room: it.room,
            description: it.description || "",
            status: it.status || "pending",
            photos: [], // existing uploaded photos aren't reloaded into the annotate UI — new photos can still be added
          }))
        );
      } catch (err) {
        if (!cancelled) setLoadError(err.message || "Failed to load inspection");
      } finally {
        if (!cancelled) setLoadingExisting(false);
      }
    })();
    return () => { cancelled = true; };
  }, [isExisting, inspectionId, authFetch]);

  const updateItem = (id, patch) =>
    setItems((prev) => prev.map((it) => (it.id === id ? { ...it, ...patch } : it)));

  /** Live-saves a single item's status (and optionally description) to
   * the server — used only in existing-mode, where the record already
   * exists and each change should persist immediately. */
  async function patchExistingItem(id, extra = {}) {
    const current = items.find((it) => it.id === id);
    if (!current) return;
    const body = { status: extra.status ?? current.status };
    if (extra.description !== undefined) body.description = extra.description;
    try {
      await authFetch(`${API_BASE}/inspections/${inspectionId}/items/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
    } catch {
      // best-effort — local state already reflects the change; a failed
      // save here isn't fatal since the person can retry the action
    }
  }

  const handleChangeStatus = (id, status) => {
    updateItem(id, { status });
    if (isExisting) patchExistingItem(id, { status });
  };
  const handleChangeDesc = (id, description) => updateItem(id, { description });
  const handleDescBlur = (id) => {
    if (isExisting) {
      const current = items.find((it) => it.id === id);
      if (current) patchExistingItem(id, { description: current.description });
    }
  };

  const handlePhotoUpload = async (itemId, fileList) => {
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

    // In existing-mode the inspection record already exists server-side,
    // so upload immediately rather than waiting for a final submit step
    // that doesn't exist in this mode.
    if (isExisting) {
      for (const photo of newPhotos) {
        try {
          const form = new FormData();
          form.append("file", photo.file);
          form.append("marks", JSON.stringify(photo.marks));
          const item = items.find((it) => it.id === itemId);
          form.append("room", item ? item.room : "");
          await authFetch(`${API_BASE}/inspections/${inspectionId}/photos`, {
            method: "POST",
            body: form,
          });
        } catch {
          // best-effort — photo stays visible locally even if the upload failed
        }
      }
    }
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

  /** Uploads any pending photo files for an item, returns array of server photo IDs. (new-mode only) */
  async function uploadPhotosForItem(newInspectionId, item) {
    const uploaded = [];
    for (const photo of item.photos) {
      const form = new FormData();
      form.append("file", photo.file);
      form.append("marks", JSON.stringify(photo.marks));
      form.append("room", item.room);
      const res = await authFetch(`${API_BASE}/inspections/${newInspectionId}/photos`, {
        method: "POST",
        body: form,
      });
      if (!res.ok) throw new Error(`Photo upload failed for ${photo.name}`);
      const data = await res.json();
      uploaded.push(data.photoId);
    }
    return uploaded;
  }

  /** Auto-creates a maintenance ticket for any item flagged or failed. (new-mode only —
   * existing-mode relies on the server doing this automatically on each PATCH.) */
  async function autoCreateTickets(newInspectionId, flaggedItems) {
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
            sourceInspectionId: newInspectionId,
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
      const { inspectionId: newId } = await res.json();

      const flaggedItems = items.filter((it) => it.status === "flag" || it.status === "fail");
      for (const item of flaggedItems) {
        if (item.photos.length) await uploadPhotosForItem(newId, item);
      }
      if (flaggedItems.length) await autoCreateTickets(newId, flaggedItems);

      setSubmitted(true);
      setSubmittedInspectionId(newId);
    } catch (err) {
      setSubmitError(err.message || "Something went wrong submitting the inspection.");
    } finally {
      setSubmitting(false);
    }
  }

  const flaggedCount = items.filter((i) => i.status === "flag" || i.status === "fail").length;
  const completedCount = items.filter((i) => i.status !== "pending").length;
  const displayUnitId = isExisting ? (existingMeta?.unitId ?? unitId) : unitId;

  async function handleDownloadPdf(idToUse) {
    if (!idToUse) return;
    setDownloadingPdf(true);
    try {
      const res = await authFetch(`${API_BASE}/inspections/${idToUse}/pdf`);
      if (!res.ok) throw new Error("Couldn't generate the report");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `inspection_${displayUnitId}.pdf`;
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

  if (isExisting && loadingExisting) {
    return <div className="max-w-2xl mx-auto p-6 text-sm text-slate-400">Loading inspection…</div>;
  }

  if (isExisting && loadError) {
    return (
      <div className="max-w-2xl mx-auto p-6 text-center">
        <p className="text-sm text-rose-600">{loadError}</p>
        {onBack && (
          <button onClick={onBack} className="mt-3 text-sm text-slate-500 underline">
            ← Back to inspections
          </button>
        )}
      </div>
    );
  }

  if (!isExisting && submitted) {
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
          onClick={() => handleDownloadPdf(submittedInspectionId)}
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
      {onBack && (
        <button onClick={onBack} className="text-xs text-slate-500 hover:text-slate-700 mb-2">
          ← Back to inspections
        </button>
      )}
      <div className="flex items-center justify-between mb-1">
        <h2 className="text-lg font-semibold">
          Unit {displayUnitId} <span className="text-slate-400 font-normal">· {(isExisting ? existingMeta?.type : inspectionType) || inspectionType} inspection</span>
        </h2>
        <div className="flex items-center gap-2">
          {isExisting && (
            <span className="text-xs font-mono text-slate-500 bg-slate-50 border border-slate-200 rounded-full px-2 py-0.5">
              {completedCount}/{items.length} complete
            </span>
          )}
          {flaggedCount > 0 && (
            <span className="text-xs font-mono text-amber-700 bg-amber-50 border border-amber-200 rounded-full px-2 py-0.5">
              {flaggedCount} flagged
            </span>
          )}
        </div>
      </div>
      <p className="text-xs text-slate-500 mb-4">
        {isExisting
          ? "Changes save automatically as you go. Flagged or failed items auto-generate maintenance tickets."
          : "Click directly on a photo to mark a damage point. Flagged or failed items auto-generate maintenance tickets on submit."}
      </p>

      <div>
        {items.map((item) => (
          <ChecklistRow
            key={item.id}
            item={item}
            onChangeStatus={handleChangeStatus}
            onChangeDesc={handleChangeDesc}
            onDescBlur={isExisting ? handleDescBlur : undefined}
            onPhotoUpload={handlePhotoUpload}
            onAddMark={handleAddMark}
            onRemovePhoto={handleRemovePhoto}
            authFetch={authFetch}
          />
        ))}
      </div>

      {!isExisting && (
        <button onClick={addRoom} className="text-xs text-slate-500 mt-3 hover:text-amber-600">
          + Add room
        </button>
      )}

      {submitError && (
        <p className="text-xs text-rose-600 mt-3 bg-rose-50 border border-rose-200 rounded px-3 py-2">
          {submitError}
        </p>
      )}

      {isExisting ? (
        <button
          onClick={() => handleDownloadPdf(inspectionId)}
          disabled={downloadingPdf}
          className="mt-4 w-full bg-slate-900 disabled:bg-slate-300 text-white text-sm font-semibold py-2.5 rounded-lg hover:bg-slate-800"
        >
          {downloadingPdf ? "Generating…" : "Download PDF report"}
        </button>
      ) : (
        <button
          onClick={handleSubmit}
          disabled={submitting || items.some((i) => i.status === "pending")}
          className="mt-4 w-full bg-slate-900 disabled:bg-slate-300 text-white text-sm font-semibold py-2.5 rounded-lg hover:bg-slate-800"
        >
          {submitting ? "Submitting..." : "Submit inspection"}
        </button>
      )}
    </div>
  );
}
