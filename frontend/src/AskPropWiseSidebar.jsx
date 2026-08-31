import { useState } from "react";
import { useAuth } from "./AuthContext";
import { API_BASE } from "./config";


const QUICK_PROMPTS = [
  "What should I focus on?",
  "Why is revenue down?",
  "Show all expiring leases.",
  "Create renewal campaign.",
];

/**
 * AskPropWiseSidebar
 *
 * Compact single-turn version of the AI Copilot for the dashboard
 * sidebar — same real backend call as AICopilot.jsx, just a smaller
 * footprint (one question, one answer, no persistent thread).
 */
export default function AskPropWiseSidebar({ propertyId }) {
  const [answer, setAnswer] = useState(null);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const { authFetch } = useAuth();

  async function ask(question) {
    const q = question.trim();
    if (!q || loading) return;
    setLoading(true);
    setError(null);
    setAnswer(null);
    try {
      const res = await authFetch(`${API_BASE}/ai/copilot`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: q, propertyId, history: [] }),
      });
      if (!res.ok) throw new Error(`Server returned ${res.status}`);
      const data = await res.json();
      setAnswer(data);
      setInput("");
    } catch (err) {
      setError("Couldn't reach the copilot.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4">
      <h3 className="text-sm font-semibold mb-2">Ask PropWise AI</h3>

      <div className="flex gap-1.5">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && ask(input)}
          placeholder="Ask PropWise AI..."
          className="flex-1 text-xs border border-slate-200 rounded-lg px-2.5 py-2"
        />
        <button
          onClick={() => ask(input)}
          disabled={loading}
          className="text-xs font-semibold bg-amber-500 disabled:bg-slate-300 text-white px-3 py-2 rounded-lg"
        >
          {loading ? "…" : "Ask"}
        </button>
      </div>

      <div className="flex flex-wrap gap-1.5 mt-2">
        {QUICK_PROMPTS.map((p) => (
          <button
            key={p}
            onClick={() => ask(p)}
            className="text-[11px] bg-slate-50 border border-slate-200 rounded-full px-2.5 py-1 hover:border-amber-400"
          >
            {p}
          </button>
        ))}
      </div>

      {error && <p className="text-xs text-rose-600 mt-2">{error}</p>}

      {answer && (
        <div className="text-xs text-slate-700 bg-slate-50 rounded-lg p-3 mt-3 leading-relaxed">
          {answer.answer}
          {answer.sources?.length > 0 && (
            <div className="text-[10px] font-mono text-slate-400 mt-1.5">
              Source: {answer.sources.join(" · ")}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
