import { useState, useRef, useEffect } from "react";
import { useAuth } from "./AuthContext";

/**
 * AICopilot
 *
 * Chat interface that calls your actual backend — no canned/mock responses.
 * The backend endpoint is expected to run its own retrieval over your
 * inspections/leases/maintenance data (e.g. via Claude with tool use / RAG)
 * and return a synthesized answer plus which sources it drew from.
 *
 * Assumption (adjust to match your actual backend):
 *   POST /api/ai/copilot
 *   body: { message, propertyId?, history: [{role, content}, ...] }
 *   response: { answer: string, sources: string[] }
 */

const API_BASE = "/api";

const SUGGESTIONS = [
  "Show vacant units",
  "Which leases are expiring soon?",
  "Summarize this week's inspections",
  "What maintenance tickets are urgent?",
];

function Message({ role, content, sources }) {
  const isUser = role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[75%] px-3.5 py-2.5 rounded-xl text-sm leading-relaxed ${
          isUser
            ? "bg-slate-900 text-white rounded-br-sm"
            : "bg-slate-100 text-slate-800 rounded-bl-sm"
        }`}
      >
        {content}
        {sources && sources.length > 0 && (
          <div className="mt-1.5 text-[10px] font-mono text-slate-400">
            Source: {sources.join(" · ")}
          </div>
        )}
      </div>
    </div>
  );
}

export default function AICopilot({ propertyId }) {
  const [messages, setMessages] = useState([
    {
      role: "assistant",
      content:
        "Hi — I can answer questions using your live inspection, lease, and maintenance data. Try one of the prompts below, or ask your own.",
    },
  ]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState(null);
  const scrollRef = useRef(null);
  const { authFetch } = useAuth();

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, sending]);

  async function sendMessage(text) {
    const trimmed = text.trim();
    if (!trimmed || sending) return;

    const nextHistory = [...messages, { role: "user", content: trimmed }];
    setMessages(nextHistory);
    setInput("");
    setSending(true);
    setError(null);

    try {
      const res = await authFetch(`${API_BASE}/ai/copilot`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: trimmed,
          propertyId,
          // send prior turns so the backend has conversational context
          history: nextHistory.slice(0, -1).map(({ role, content }) => ({ role, content })),
        }),
      });
      if (!res.ok) throw new Error(`Server returned ${res.status}`);
      const data = await res.json();
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: data.answer, sources: data.sources },
      ]);
    } catch (err) {
      setError("Couldn't reach the copilot backend. Check that /api/ai/copilot is running.");
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="max-w-2xl mx-auto p-5 bg-white rounded-xl border border-slate-200 flex flex-col">
      <h2 className="text-lg font-semibold mb-1">AI Copilot</h2>
      <p className="text-xs text-slate-500 mb-3">
        Ask about vacancies, leases, inspections, or maintenance across your portfolio.
      </p>

      <div
        ref={scrollRef}
        className="flex-1 h-80 overflow-y-auto bg-slate-50 rounded-lg border border-slate-200 p-4 flex flex-col gap-2.5"
      >
        {messages.map((m, i) => (
          <Message key={i} role={m.role} content={m.content} sources={m.sources} />
        ))}
        {sending && (
          <div className="flex justify-start">
            <div className="bg-slate-100 text-slate-400 text-sm px-3.5 py-2.5 rounded-xl rounded-bl-sm">
              Thinking…
            </div>
          </div>
        )}
      </div>

      {error && (
        <p className="text-xs text-rose-600 bg-rose-50 border border-rose-200 rounded px-3 py-2 mt-3">
          {error}
        </p>
      )}

      <div className="flex flex-wrap gap-1.5 mt-3">
        {SUGGESTIONS.map((s) => (
          <button
            key={s}
            onClick={() => sendMessage(s)}
            className="text-xs bg-white border border-slate-200 rounded-full px-3 py-1.5 hover:border-amber-400 hover:text-amber-700"
          >
            {s}
          </button>
        ))}
      </div>

      <div className="flex gap-2 mt-3">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && sendMessage(input)}
          placeholder="Ask anything about your portfolio..."
          className="flex-1 text-sm border border-slate-200 rounded-lg px-3 py-2.5"
        />
        <button
          onClick={() => sendMessage(input)}
          disabled={sending || !input.trim()}
          className="bg-amber-500 disabled:bg-slate-200 text-white text-sm font-semibold px-4 py-2.5 rounded-lg hover:bg-amber-600"
        >
          Ask
        </button>
      </div>
    </div>
  );
}
