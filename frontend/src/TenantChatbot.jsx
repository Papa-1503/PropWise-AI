import { useState, useRef, useEffect } from "react";
import { Sparkles, Send, Wrench } from "lucide-react";
import { useAuth } from "./AuthContext";
import { API_BASE } from "./config";

/**
 * TenantChatbot
 *
 * The real, resident-facing counterpart to AICopilot.jsx (staff-only)
 * - calls the real, correctly-scoped POST /api/ai/faq, never
 * /api/ai/copilot. This fixes a real, previously-live bug: the "ai"
 * tab used to route EVERY role, tenants included, to AICopilot.jsx,
 * which always called the staff-scoped /copilot endpoint - see
 * App.jsx's own routing fix alongside this file for the other half
 * of that real fix.
 *
 * Genuinely agentic, not just Q&A - a resident describing a real
 * problem ("my kitchen faucet won't stop leaking") gets an actual
 * maintenance request submitted on their behalf via the backend's
 * real submit_maintenance_request tool, not just instructions on how
 * to use the maintenance form. ticketCreated in the response drives
 * a real, visible confirmation below so this doesn't happen silently.
 */

const SUGGESTIONS = [
  "How much is my rent and when is it due?",
  "My kitchen faucet is leaking",
  "What's the status of my maintenance request?",
  "When does my lease end?",
];

function Message({ role, content, ticketCreated }) {
  const isUser = role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div className="max-w-[85%]">
        <div
          className={`text-sm rounded-2xl px-4 py-2.5 whitespace-pre-wrap ${
            isUser ? "bg-indigo-600 text-white" : "bg-slate-100 text-slate-800"
          }`}
        >
          {content}
        </div>
        {ticketCreated && (
          <div className="flex items-center gap-1.5 text-xs text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-full px-3 py-1 mt-1.5 w-fit">
            <Wrench size={12} />
            Maintenance request submitted
          </div>
        )}
      </div>
    </div>
  );
}

export default function TenantChatbot() {
  const { authFetch } = useAuth();
  const [messages, setMessages] = useState([
    { role: "assistant", content: "Hi! I can answer questions about your lease and maintenance requests, and I can submit a new maintenance request for you if something needs fixing. What can I help with?" },
  ]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState(null);
  const scrollRef = useRef(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  async function handleSend(text) {
    const message = (text ?? input).trim();
    if (!message || sending) return;
    setInput("");
    setError(null);
    setSending(true);
    const newMessages = [...messages, { role: "user", content: message }];
    setMessages(newMessages);

    try {
      const res = await authFetch(`${API_BASE}/ai/faq`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message,
          history: messages.map((m) => ({ role: m.role, content: m.content })),
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Something went wrong.");
      setMessages((prev) => [...prev, { role: "assistant", content: data.answer, ticketCreated: data.ticketCreated }]);
    } catch (err) {
      setError(err.message || "Couldn't reach the assistant — try again in a moment.");
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

  const isFirstMessage = messages.length === 1;

  return (
    <div className="max-w-2xl mx-auto">
      <div className="flex items-center gap-2 mb-3">
        <Sparkles size={18} className="text-indigo-600" />
        <h2 className="text-lg font-semibold">Ask PropWise AI</h2>
      </div>

      <div className="bg-white border border-slate-200 rounded-xl flex flex-col" style={{ height: "60vh" }}>
        <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
          {messages.map((m, i) => (
            <Message key={i} role={m.role} content={m.content} ticketCreated={m.ticketCreated} />
          ))}
          {sending && (
            <div className="flex justify-start">
              <div className="bg-slate-100 text-slate-400 text-sm rounded-2xl px-4 py-2.5">Thinking…</div>
            </div>
          )}
        </div>

        {isFirstMessage && (
          <div className="px-4 pb-2 flex flex-wrap gap-1.5">
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                onClick={() => handleSend(s)}
                className="text-xs text-indigo-700 bg-indigo-50 hover:bg-indigo-100 rounded-full px-3 py-1"
              >
                {s}
              </button>
            ))}
          </div>
        )}

        {error && (
          <p role="alert" className="text-xs text-rose-600 bg-rose-50 border-t border-rose-200 px-4 py-2">{error}</p>
        )}

        <div className="flex items-center gap-2 px-4 py-3 border-t border-slate-100">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={sending}
            placeholder="Ask a question, or describe a maintenance problem…"
            className="flex-1 text-sm border border-slate-200 rounded-full px-4 py-2 disabled:bg-slate-50"
          />
          <button
            onClick={() => handleSend()}
            disabled={sending || !input.trim()}
            className="w-9 h-9 shrink-0 rounded-full bg-indigo-600 disabled:bg-indigo-300 text-white flex items-center justify-center"
          >
            <Send size={15} />
          </button>
        </div>
      </div>
    </div>
  );
}
