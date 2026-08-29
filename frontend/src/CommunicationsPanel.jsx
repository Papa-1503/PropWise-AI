import { useState, useEffect, useCallback, useId } from "react";
import { useAuth } from "./AuthContext";
import EmptyState from "./EmptyState";
import { MessageSquare, Phone, Mail, Plus, X, ArrowUpRight, ArrowDownLeft } from "lucide-react";
import { API_BASE } from "./config";

/**
 * CommunicationsPanel
 *
 * The frontend for the Communication Hub (Priority 12) — the backend
 * (routers/communications.py) has worked and been tested since earlier
 * today, but had no UI anywhere. Same gap pattern as Inspections and
 * the Owner Portal before it: a real, working backend nobody could
 * actually use.
 *
 * Two ways to add an entry:
 *   - "Log communication" — records something that happened outside the
 *     app (a phone call, an in-person conversation), or a manual note.
 *   - "Send email" — actually sends via the real email service and logs
 *     it. Note: as of today this will fail with a clean, honest error
 *     until Mailgun's custom-domain requirement is resolved (Priority
 *     12's known external blocker) — that's expected, not a bug here.
 */

const CHANNEL_ICON = { email: Mail, sms: MessageSquare, call: Phone };
const CHANNEL_LABEL = { email: "Email", sms: "SMS", call: "Call" };

function ComposeModal({ propertyId, onClose, onSaved, mode }) {
  const [unitId, setUnitId] = useState("");
  const [channel, setChannel] = useState("call");
  const [direction, setDirection] = useState("outbound");
  const [to, setTo] = useState("");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const { authFetch } = useAuth();
  const idPrefix = useId();

  async function handleSave() {
    if (!unitId.trim() || !body.trim()) {
      setError("Unit and a description are required.");
      return;
    }
    if (mode === "email" && !to.trim()) {
      setError("Recipient email is required.");
      return;
    }
    if (mode === "sms" && !to.trim()) {
      setError("Recipient phone number is required.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const endpoint =
        mode === "email" ? "/communications/send-email" : mode === "sms" ? "/communications/send-sms" : "/communications";
      const payload =
        mode === "email"
          ? { propertyId, unitId, to, subject, body }
          : mode === "sms"
          ? { propertyId, unitId, to, body }
          : { propertyId, unitId, channel, direction, subject: subject || undefined, body };

      const res = await authFetch(`${API_BASE}${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
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
          <h3 className="font-semibold">{mode === "email" ? "Send email" : mode === "sms" ? "Send SMS" : "Log communication"}</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600">
            <X size={18} />
          </button>
        </div>

        <div className="space-y-3">
          <div>
            <label htmlFor={`${idPrefix}-unit`} className="text-xs text-slate-500">Unit</label>
            <input
              id={`${idPrefix}-unit`}
              value={unitId}
              onChange={(e) => setUnitId(e.target.value)}
              placeholder="e.g. 104"
              className="w-full text-sm border border-slate-200 rounded px-2 py-1.5 mt-0.5"
            />
          </div>

          {mode === "email" ? (
            <div>
              <label htmlFor={`${idPrefix}-to`} className="text-xs text-slate-500">To (email address)</label>
              <input
                id={`${idPrefix}-to`}
                type="email"
                value={to}
                onChange={(e) => setTo(e.target.value)}
                placeholder="tenant@example.com"
                className="w-full text-sm border border-slate-200 rounded px-2 py-1.5 mt-0.5"
              />
            </div>
          ) : mode === "sms" ? (
            <div>
              <label htmlFor={`${idPrefix}-to`} className="text-xs text-slate-500">To (phone number)</label>
              <input
                id={`${idPrefix}-to`}
                type="tel"
                value={to}
                onChange={(e) => setTo(e.target.value)}
                placeholder="+15551234567"
                className="w-full text-sm border border-slate-200 rounded px-2 py-1.5 mt-0.5"
              />
            </div>
          ) : (
            <div className="flex gap-3">
              <div className="flex-1">
                <label htmlFor={`${idPrefix}-channel`} className="text-xs text-slate-500">Channel</label>
                <select
                  id={`${idPrefix}-channel`}
                  value={channel}
                  onChange={(e) => setChannel(e.target.value)}
                  className="w-full text-sm border border-slate-200 rounded px-2 py-1.5 mt-0.5"
                >
                  <option value="call">Call</option>
                  <option value="sms">SMS</option>
                  <option value="email">Email (logged only)</option>
                </select>
              </div>
              <div className="flex-1">
                <label htmlFor={`${idPrefix}-direction`} className="text-xs text-slate-500">Direction</label>
                <select
                  id={`${idPrefix}-direction`}
                  value={direction}
                  onChange={(e) => setDirection(e.target.value)}
                  className="w-full text-sm border border-slate-200 rounded px-2 py-1.5 mt-0.5"
                >
                  <option value="outbound">Outbound</option>
                  <option value="inbound">Inbound</option>
                </select>
              </div>
            </div>
          )}

          {mode !== "sms" && (
            <div>
              <label htmlFor={`${idPrefix}-subject`} className="text-xs text-slate-500">Subject {mode !== "email" && "(optional)"}</label>
              <input
                id={`${idPrefix}-subject`}
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
                className="w-full text-sm border border-slate-200 rounded px-2 py-1.5 mt-0.5"
              />
            </div>
          )}

          <div>
            <label htmlFor={`${idPrefix}-body`} className="text-xs text-slate-500">{mode === "email" || mode === "sms" ? "Message" : "What happened"}</label>
            <textarea
              id={`${idPrefix}-body`}
              value={body}
              onChange={(e) => setBody(e.target.value)}
              rows={4}
              className="w-full text-sm border border-slate-200 rounded px-2 py-1.5 mt-0.5"
            />
          </div>
        </div>

        {error && (
          <p className="text-xs text-rose-600 mt-3 bg-rose-50 border border-rose-200 rounded px-3 py-2">{error}</p>
        )}

        <button
          onClick={handleSave}
          disabled={saving}
          className="mt-4 w-full bg-slate-900 disabled:bg-slate-300 text-white text-sm font-semibold py-2.5 rounded-lg hover:bg-slate-800"
        >
          {saving ? "Saving…" : mode === "email" || mode === "sms" ? "Send" : "Log it"}
        </button>
      </div>
    </div>
  );
}

function CommRow({ comm, buildingName }) {
  const Icon = CHANNEL_ICON[comm.channel] || MessageSquare;
  const DirIcon = comm.direction === "inbound" ? ArrowDownLeft : ArrowUpRight;
  return (
    <div className="border-b border-slate-100 py-3 last:border-none flex items-start gap-3">
      <div className="mt-0.5 text-slate-400">
        <Icon size={16} />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 text-sm">
          <span className="font-medium">{CHANNEL_LABEL[comm.channel] || comm.channel}</span>
          <DirIcon size={12} className={comm.direction === "inbound" ? "text-emerald-500" : "text-slate-400"} />
          {comm.status === "failed" && (
            <span className="text-[10px] font-mono uppercase text-rose-600 bg-rose-50 border border-rose-200 rounded px-1.5">
              failed
            </span>
          )}
        </div>
        {comm.subject && <p className="text-sm text-slate-700 mt-0.5">{comm.subject}</p>}
        <p className="text-sm text-slate-600 mt-0.5">{comm.body}</p>
        <p className="text-xs text-slate-400 mt-1">
          {buildingName && <span>{buildingName} · </span>}
          Unit {comm.unitId} · {comm.loggedBy || "system"} ·{" "}
          {comm.createdAt ? new Date(comm.createdAt).toLocaleString() : ""}
        </p>
      </div>
    </div>
  );
}

export default function CommunicationsPanel({ propertyId }) {
  const [comms, setComms] = useState([]);
  const [loading, setLoading] = useState(true);
  const [composeMode, setComposeMode] = useState(null); // null | "log" | "email" | "sms"
  const [error, setError] = useState(null);
  const { authFetch, getPropertyName } = useAuth();

  const fetchComms = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (propertyId) params.set("propertyId", propertyId);
      const res = await authFetch(`${API_BASE}/communications?${params.toString()}`);
      if (res.ok) {
        const data = await res.json();
        setComms(data.communications || []);
      } else {
        setError(res.status === 403 ? "You don't have access to this." : "Couldn't load communications — try again.");
      }
    } catch {
      setError("Couldn't load communications — check your connection and try again.");
    } finally {
      setLoading(false);
    }
  }, [propertyId, authFetch]);

  useEffect(() => {
    fetchComms();
  }, [fetchComms]);

  return (
    <div className="max-w-2xl mx-auto">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-lg font-semibold">Communications</h2>
        <div className="flex gap-2">
          <button
            onClick={() => setComposeMode("log")}
            disabled={!propertyId}
            title={!propertyId ? "Pick a specific building first" : undefined}
            className="flex items-center gap-1.5 text-sm font-semibold bg-white border border-slate-200 text-slate-700 px-3 py-1.5 rounded-lg hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <Plus size={14} />
            Log
          </button>
          <button
            onClick={() => setComposeMode("email")}
            disabled={!propertyId}
            title={!propertyId ? "Pick a specific building first" : undefined}
            className="flex items-center gap-1.5 text-sm font-semibold bg-slate-900 text-white px-3 py-1.5 rounded-lg hover:bg-slate-800 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <Mail size={14} />
            Send email
          </button>
          <button
            onClick={() => setComposeMode("sms")}
            disabled={!propertyId}
            title={!propertyId ? "Pick a specific building first" : undefined}
            className="flex items-center gap-1.5 text-sm font-semibold bg-indigo-600 text-white px-3 py-1.5 rounded-lg hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <MessageSquare size={14} />
            Send SMS
          </button>
        </div>
      </div>

      {!propertyId && (
        <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 mb-3">
          Logging and sending require a specific building — pick one from the selector in the header first.
        </p>
      )}

      {loading ? (
        <div className="h-40 bg-slate-100 rounded-xl animate-pulse" />
      ) : error ? (
        <p role="alert" aria-live="polite" className="text-sm text-rose-600 bg-rose-50 border border-rose-200 rounded-xl px-4 py-3">{error}</p>
      ) : comms.length === 0 ? (
        <EmptyState
          icon={MessageSquare}
          title="No communications yet"
          subtitle="Calls, texts, and emails with residents will show up here as one merged timeline."
        />
      ) : (
        <div className="bg-white border border-slate-200 rounded-xl px-4">
          {comms.map((c) => (
            <CommRow key={c.id} comm={c} buildingName={!propertyId ? getPropertyName(c.propertyId) : null} />
          ))}
        </div>
      )}

      {composeMode && (
        <ComposeModal
          propertyId={propertyId}
          mode={composeMode}
          onClose={() => setComposeMode(null)}
          onSaved={fetchComms}
        />
      )}
    </div>
  );
}
