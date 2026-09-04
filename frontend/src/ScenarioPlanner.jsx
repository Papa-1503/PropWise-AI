import { useState, useRef, useEffect } from "react";
import { useAuth } from "./AuthContext";
import { API_BASE } from "./config";

/**
 * ScenarioPlanner
 *
 * Interactive "what if" AI for staff — distinct from AICopilot.jsx:
 * that's general Q&A over a text context blob, this is specifically
 * for financial what-if questions (rent changes, occupancy shifts)
 * where the backend runs real tool-use over deterministic math
 * (scenario_service.py), not free-text-generated numbers. The
 * computedData panel below renders those real numbers directly, so
 * staff see the actual figures the AI's answer was grounded in, not
 * just prose that claims them.
 *
 * POST /api/ai/scenario
 * body: { message, propertyId?, history: [{role, content}, ...] }
 * response: { answer, sources: string[], computedData: object | null }
 */

const SUGGESTIONS = [
  "If I raise rent 5%, what happens?",
  "What if 3 more units go vacant?",
  "What's my current occupancy and rent roll?",
  "What if I fill 4 vacancies?",
];

function formatKey(key) {
  // camelCase -> "Camel Case", for a readable label from a raw API key
  return key.replace(/([A-Z])/g, " $1").replace(/^./, (c) => c.toUpperCase());
}

function formatValue(key, value) {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number") {
    const lower = key.toLowerCase();
    if (lower.includes("dollar") || lower.includes("rent") || lower.includes("revenue") || lower.includes("balance")) {
      return `$${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
    }
    if (lower.includes("pct") || lower.includes("percent")) return `${value}%`;
    return value.toLocaleString();
  }
  return String(value);
}

function ComputedDataPanel({ data }) {
  if (!data) return null;
  const entries = Object.entries(data).filter(
    ([k, v]) => k !== "exampleUnits" && k !== "note" && v !== null && typeof v !== "object"
  );
  return (
    <div className="bg-indigo-50/60 border border-indigo-100 rounded-lg px-3 py-2.5 text-xs">
      <div className="grid grid-cols-2 gap-x-4 gap-y-1">
        {entries.map(([k, v]) => (
          <div key={k} className="flex justify-between gap-2">
            <span className="text-slate-500">{formatKey(k)}</span>
            <span className="font-medium text-slate-800">{formatValue(k, v)}</span>
          </div>
        ))}
      </div>
      {Array.isArray(data.exampleUnits) && data.exampleUnits.length > 0 && (
        <div className="mt-2 pt-2 border-t border-indigo-100">
          <p className="text-slate-500 mb-1">Example units:</p>
          {data.exampleUnits.map((u, i) => (
            <div key={i} className="flex justify-between text-slate-600">
              <span>{u.propertyName} · Unit {u.unitId}</span>
              <span>${u.currentRent.toLocaleString()} → ${u.newRent.toLocaleString()}</span>
            </div>
          ))}
        </div>
      )}
      {data.note && <p className="mt-2 pt-2 border-t border-indigo-100 text-amber-700">{data.note}</p>}
    </div>
  );
}

function Message({ role, content, sources, computedData }) {
  const isUser = role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div className={`max-w-[85%] ${isUser ? "" : "w-full"}`}>
        <div
          className={`px-3.5 py-2.5 rounded-xl text-sm leading-relaxed ${
            isUser
              ? "bg-slate-900 text-white rounded-br-sm"
              : "bg-slate-100 text-slate-800 rounded-bl-sm"
          }`}
        >
          {content}
          {sources && sources.length > 0 && (
            <div className="mt-1.5 text-[10px] font-mono text-slate-400">
              Computed via: {sources.join(" · ")}
            </div>
          )}
        </div>
        {!isUser && computedData && (
          <div className="mt-1.5">
            <ComputedDataPanel data={computedData} />
          </div>
        )}
      </div>
    </div>
  );
}

export default function ScenarioPlanner({ propertyId }) {
  const [messages, setMessages] = useState([
    {
      role: "assistant",
      content:
        "Ask me a what-if question about rent or occupancy — I'll compute real numbers from your live portfolio, not a guess. Try one of the prompts below, or ask your own.",
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
      const res = await authFetch(`${API_BASE}/ai/scenario`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: trimmed,
          propertyId,
          history: nextHistory.slice(0, -1).map(({ role, content }) => ({ role, content })),
        }),
      });
      if (!res.ok) throw new Error(`Server returned ${res.status}`);
      const data = await res.json();
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: data.answer, sources: data.sources, computedData: data.computedData },
      ]);
    } catch (err) {
      setError("Couldn't reach the scenario planner. Check that /api/ai/scenario is running.");
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="max-w-2xl mx-auto p-5 bg-white rounded-xl border border-slate-200 flex flex-col">
      <h2 className="text-lg font-semibold mb-1">Scenario Planner</h2>
      <p className="text-xs text-slate-500 mb-3">
        Ask what-if questions about rent changes or occupancy — every answer is grounded in real, computed numbers from your portfolio.
      </p>

      <div
        ref={scrollRef}
        className="flex-1 h-96 overflow-y-auto bg-slate-50 rounded-lg border border-slate-200 p-4 flex flex-col gap-3"
      >
        {messages.map((m, i) => (
          <Message key={i} role={m.role} content={m.content} sources={m.sources} computedData={m.computedData} />
        ))}
        {sending && (
          <div className="flex justify-start">
            <div className="bg-slate-100 text-slate-400 text-sm px-3.5 py-2.5 rounded-xl rounded-bl-sm">
              Computing…
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
            className="text-xs bg-white border border-slate-200 rounded-full px-3 py-1.5 hover:border-indigo-400 hover:text-indigo-700"
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
          placeholder="Ask a what-if question..."
          className="flex-1 text-sm border border-slate-200 rounded-lg px-3 py-2.5"
        />
        <button
          onClick={() => sendMessage(input)}
          disabled={sending || !input.trim()}
          className="bg-indigo-600 disabled:bg-slate-200 text-white text-sm font-semibold px-4 py-2.5 rounded-lg hover:bg-indigo-700"
        >
          Ask
        </button>
      </div>
    </div>
  );
}
