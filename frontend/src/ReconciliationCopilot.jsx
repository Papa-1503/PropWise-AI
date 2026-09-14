import { useState, useEffect, useRef } from "react";
import { Sparkles, Send, ChevronDown, ChevronUp } from "lucide-react";
import { useAuth } from "./AuthContext";
import { API_BASE } from "./config";

/**
 * ReconciliationCopilot
 *
 * Real, conversational reconciliation guide for backend
 * routers/reconciliation_assistant.py - the second feature built on
 * the same real agentic tool-calling pattern OnboardingAssistant.jsx
 * established (see that component's own docstring). Unlike the
 * onboarding assistant (which disappears once setup is done), this
 * one is a real, ongoing tool - reconciliation is a recurring task,
 * not a one-time setup step, so it stays available as a collapsible
 * panel rather than vanishing after first use.
 *
 * onLineMatched fires after every exchange so the parent Reconciliation
 * page can refresh its own real manual list (fetchLines) - the two
 * views (chat and manual table) share the exact same underlying real
 * data, so a match made in chat must be immediately visible in the
 * table too, never a separately-tracked, out-of-sync view.
 */
export default function ReconciliationCopilot({ onLineMatched }) {
  const { authFetch } = useAuth();
  const [expanded, setExpanded] = useState(false);
  const [unmatchedCount, setUnmatchedCount] = useState(null);
  const [messages, setMessages] = useState([
    { role: "assistant", content: "Hi! I can help you match your unmatched bank statement lines to charges. Want to start?" },
  ]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const scrollRef = useRef(null);

  useEffect(() => {
    authFetch(`${API_BASE}/reconciliation-assistant/status`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => data && setUnmatchedCount(data.unmatchedCount))
      .catch(() => {});
  }, [authFetch]);

  useEffect(() => {
    if (expanded) scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, expanded]);

  async function handleSend() {
    const message = input.trim();
    if (!message || sending) return;
    setInput("");
    setSending(true);
    const newMessages = [...messages, { role: "user", content: message }];
    setMessages(newMessages);

    try {
      const res = await authFetch(`${API_BASE}/reconciliation-assistant/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message,
          history: messages.filter((_, i) => i > 0).map((m) => ({ role: m.role, content: m.content })),
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Something went wrong.");
      setMessages((prev) => [...prev, { role: "assistant", content: data.reply }]);
      setUnmatchedCount(data.unmatchedCount);
      onLineMatched?.();
    } catch (err) {
      setMessages((prev) => [...prev, { role: "assistant", content: `Sorry, something went wrong: ${err.message}` }]);
    } finally {
      setSending(false);
    }
  }

  function handleKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  if (unmatchedCount === 0) return null; // nothing to reconcile - stay out of the way

  return (
    <div className="bg-white border border-indigo-200 rounded-2xl shadow-sm overflow-hidden mb-3">
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full bg-gradient-to-r from-indigo-600 to-fuchsia-600 px-5 py-3 flex items-center justify-between gap-2"
      >
        <span className="flex items-center gap-2">
          <Sparkles size={18} className="text-white" />
          <h3 className="text-sm font-semibold text-white">
            Reconciliation copilot{unmatchedCount != null ? ` — ${unmatchedCount} unmatched` : ""}
          </h3>
        </span>
        {expanded ? <ChevronUp size={16} className="text-white" /> : <ChevronDown size={16} className="text-white" />}
      </button>

      {expanded && (
        <>
          <div ref={scrollRef} className="max-h-72 overflow-y-auto px-5 py-4 space-y-3">
            {messages.map((m, i) => (
              <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
                <div
                  className={`max-w-[80%] text-sm rounded-2xl px-3.5 py-2 whitespace-pre-wrap ${
                    m.role === "user" ? "bg-indigo-600 text-white" : "bg-slate-100 text-slate-800"
                  }`}
                >
                  {m.content}
                </div>
              </div>
            ))}
            {sending && (
              <div className="flex justify-start">
                <div className="bg-slate-100 text-slate-400 text-sm rounded-2xl px-3.5 py-2">Thinking…</div>
              </div>
            )}
          </div>

          <div className="flex items-center gap-2 px-4 py-3 border-t border-slate-100">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={sending}
              placeholder="Type your reply…"
              className="flex-1 text-sm border border-slate-200 rounded-full px-4 py-2 disabled:bg-slate-50"
            />
            <button
              onClick={handleSend}
              disabled={sending || !input.trim()}
              className="w-9 h-9 shrink-0 rounded-full bg-indigo-600 disabled:bg-indigo-300 text-white flex items-center justify-center"
            >
              <Send size={15} />
            </button>
          </div>
        </>
      )}
    </div>
  );
}
