import { useState, useEffect, useRef } from "react";
import { Sparkles, Send, ChevronDown, ChevronUp } from "lucide-react";
import { useAuth } from "./AuthContext";
import { API_BASE } from "./config";

/**
 * VendorAssistant
 *
 * Real, conversational vendor-adding guide for backend
 * routers/vendor_assistant.py - the third feature built on the same
 * real agentic tool-calling pattern (see OnboardingAssistant.jsx and
 * ReconciliationCopilot.jsx). Stays available as a collapsible panel
 * like the reconciliation copilot (never a one-time-only card like
 * the onboarding assistant) - unlike reconciliation, there's no real
 * "done" state for a vendor roster (staff can always want to add
 * another one), so this never auto-hides based on count.
 *
 * onVendorAdded fires after every exchange so the parent VendorsList
 * page can refresh its own real roster (fetchVendors) - the chat and
 * the manual "New vendor" form both write to the same real data.
 */
export default function VendorAssistant({ onVendorAdded }) {
  const { authFetch } = useAuth();
  const [expanded, setExpanded] = useState(false);
  const [vendorCount, setVendorCount] = useState(null);
  const [messages, setMessages] = useState([
    { role: "assistant", content: "Hi! Want to add a vendor? Just tell me their name, what kind of work they do, and how to reach them." },
  ]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const scrollRef = useRef(null);

  useEffect(() => {
    authFetch(`${API_BASE}/vendor-assistant/status`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => data && setVendorCount(data.vendorCount))
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
      const res = await authFetch(`${API_BASE}/vendor-assistant/chat`, {
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
      setVendorCount(data.vendorCount);
      onVendorAdded?.();
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

  return (
    <div className="bg-white border border-indigo-200 rounded-2xl shadow-sm overflow-hidden mb-3">
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full bg-gradient-to-r from-indigo-600 to-fuchsia-600 px-5 py-3 flex items-center justify-between gap-2"
      >
        <span className="flex items-center gap-2">
          <Sparkles size={18} className="text-white" />
          <h3 className="text-sm font-semibold text-white">
            Add a vendor with AI{vendorCount != null ? ` — ${vendorCount} on file` : ""}
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
              placeholder="e.g. Acme Plumbing, 612-555-0100"
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
