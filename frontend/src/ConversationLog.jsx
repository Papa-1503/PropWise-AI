import { useState, useEffect, useCallback } from "react";
import { useAuth } from "./AuthContext";
import { API_BASE } from "./config";
import EmptyState from "./EmptyState";
import { MessageSquare, PhoneCall, ChevronDown, ChevronUp } from "lucide-react";

/**
 * ConversationLog
 *
 * The staff-facing view of real AI triage conversations - the other
 * half of both the AI phone-triage and two-way SMS features, which
 * always stored the full real Q&A (voice_triage_col, sms_triage_col)
 * but had no frontend view of it, only the resulting ticket. Two
 * tabs, one real backend list each - kept as genuinely separate
 * conversations (not merged into one feed) since a call and a text
 * are different media with different fields (a call has a recording/
 * dial outcome, a text doesn't).
 */

const SEVERITY_STYLE = {
  emergency: "bg-red-100 text-red-800",
  urgent: "bg-rose-50 text-rose-700",
  low: "bg-slate-50 text-slate-500",
  routine: "bg-slate-50 text-slate-500",
};

function ConversationCard({ item, kind }) {
  const [expanded, setExpanded] = useState(false);
  const turns = item.turns || [];

  return (
    <div className="border border-slate-200 rounded-lg px-3 py-2.5">
      <button onClick={() => setExpanded((e) => !e)} className="w-full flex items-center justify-between text-left">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-medium">
              {item.propertyName || "Unknown building"}
              {item.unitId || item.knownUnit ? ` · Unit ${item.unitId || item.knownUnit}` : ""}
            </span>
            {item.severityTier && (
              <span className={`text-[10px] font-mono uppercase px-2 py-0.5 rounded-full ${SEVERITY_STYLE[item.severityTier] || "bg-slate-50 text-slate-500"}`}>
                {item.severityTier}
              </span>
            )}
            {kind === "sms" && !item.concluded && (
              <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded-full bg-amber-50 text-amber-700">
                in progress
              </span>
            )}
          </div>
          <p className="text-xs text-slate-400 mt-0.5">
            {kind === "voice" ? item.callerNumber : item.phone}
            {item.residentName || item.matchedResidentName ? ` · ${item.residentName || item.matchedResidentName}` : ""}
            {" · "}
            {item.createdAt ? new Date(item.createdAt).toLocaleString() : ""}
          </p>
        </div>
        {expanded ? <ChevronUp size={16} className="text-slate-400 shrink-0" /> : <ChevronDown size={16} className="text-slate-400 shrink-0" />}
      </button>

      {expanded && (
        <div className="mt-2 pt-2 border-t border-slate-100 space-y-2">
          {turns.length === 0 ? (
            <p className="text-xs text-slate-400">No conversation turns recorded.</p>
          ) : (
            turns.map((t, i) => (
              <div key={i} className="text-xs">
                <p className="text-slate-500 italic">{t.question}</p>
                <p className="text-slate-800 mt-0.5">{t.answer || <span className="text-slate-300">(no response)</span>}</p>
              </div>
            ))
          )}
          {item.ticketId && (
            <p className="text-[11px] text-indigo-700 pt-1">Ticket created — see the Maintenance tab for status.</p>
          )}
        </div>
      )}
    </div>
  );
}

export default function ConversationLog() {
  const [tab, setTab] = useState("voice");
  const [voiceLog, setVoiceLog] = useState(null);
  const [smsLog, setSmsLog] = useState(null);
  const [error, setError] = useState(null);
  const { authFetch } = useAuth();

  const fetchLogs = useCallback(async () => {
    setError(null);
    try {
      const [voiceRes, smsRes] = await Promise.all([
        authFetch(`${API_BASE}/telephony/triage-log`),
        authFetch(`${API_BASE}/sms/log`),
      ]);
      if (!voiceRes.ok || !smsRes.ok) throw new Error("Couldn't load conversation logs.");
      const voiceData = await voiceRes.json();
      const smsData = await smsRes.json();
      setVoiceLog(voiceData.triageLog || []);
      setSmsLog(smsData.smsLog || []);
    } catch (err) {
      setError(err.message);
    }
  }, [authFetch]);

  useEffect(() => {
    fetchLogs();
  }, [fetchLogs]);

  const items = tab === "voice" ? voiceLog : smsLog;

  return (
    <div className="max-w-2xl mx-auto p-5 bg-white rounded-xl border border-slate-200">
      <h2 className="text-lg font-semibold mb-1">Conversation Log</h2>
      <p className="text-xs text-slate-500 mb-4">
        Real AI triage conversations from after-hours calls and text-ins — what was asked, what was answered,
        and the ticket it led to.
      </p>

      <div className="flex gap-1 mb-3">
        <button
          onClick={() => setTab("voice")}
          className={`flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-full ${
            tab === "voice" ? "bg-slate-900 text-white" : "border border-slate-200 text-slate-500"
          }`}
        >
          <PhoneCall size={12} />
          Calls
        </button>
        <button
          onClick={() => setTab("sms")}
          className={`flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-full ${
            tab === "sms" ? "bg-slate-900 text-white" : "border border-slate-200 text-slate-500"
          }`}
        >
          <MessageSquare size={12} />
          Texts
        </button>
      </div>

      {error && (
        <p role="alert" className="text-sm text-rose-600 bg-rose-50 border border-rose-200 rounded-xl px-4 py-3">
          {error}
        </p>
      )}

      {!error && items === null && <div className="h-32 bg-slate-100 rounded-xl animate-pulse" />}

      {!error && items !== null && items.length === 0 && (
        <EmptyState
          icon={tab === "voice" ? PhoneCall : MessageSquare}
          title={tab === "voice" ? "No calls logged yet" : "No texts logged yet"}
          subtitle={
            tab === "voice"
              ? "After-hours AI-triaged calls will show up here."
              : "Inbound text conversations will show up here."
          }
        />
      )}

      {!error && items && items.length > 0 && (
        <div className="space-y-2">
          {items.map((item) => (
            <ConversationCard key={item.id} item={item} kind={tab} />
          ))}
        </div>
      )}
    </div>
  );
}
