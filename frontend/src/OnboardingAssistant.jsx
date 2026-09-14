import { useState, useEffect, useRef } from "react";
import { Sparkles, Send, CheckCircle2, Circle } from "lucide-react";
import { useAuth } from "./AuthContext";
import { API_BASE } from "./config";

/**
 * OnboardingAssistant
 *
 * Real, conversational setup guide for backend routers/onboarding_assistant.py -
 * genuinely new pattern for this app's frontend, matching the new
 * agentic tool-calling pattern on the backend: this isn't just a chat
 * window that explains what to do, it's a chat window where the
 * assistant actually creates the property/lease as the person
 * describes it, then the UI reflects the real, resulting state
 * (status.propertyCount / leaseCount) - never a separately-tracked,
 * staleable "did they finish" flag of its own.
 *
 * Only rendered when setup is genuinely incomplete (see DashboardTab's
 * own conditional render) - once a real property and a real lease
 * exist, this card disappears entirely rather than lingering as dead
 * UI once its job is done.
 */
export default function OnboardingAssistant({ onSetupComplete }) {
  const { authFetch } = useAuth();
  const [status, setStatus] = useState(null);
  const [messages, setMessages] = useState([
    { role: "assistant", content: "Hi! I'll help you get PropWise AI set up. Let's start with your first property — what's it called, and what's its address?" },
  ]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const scrollRef = useRef(null);

  useEffect(() => {
    authFetch(`${API_BASE}/onboarding/status`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => data && setStatus(data))
      .catch(() => {});
  }, [authFetch]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  async function handleSend() {
    const message = input.trim();
    if (!message || sending) return;
    setInput("");
    setSending(true);
    const newMessages = [...messages, { role: "user", content: message }];
    setMessages(newMessages);

    try {
      const res = await authFetch(`${API_BASE}/onboarding/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message,
          // Real conversation history, matching the backend's own
          // {role, content} shape - the very first assistant greeting
          // above is a client-side UI convenience only and is
          // deliberately NOT sent, since the backend's own system
          // prompt already establishes that same opening framing.
          history: messages.filter((_, i) => i > 0).map((m) => ({ role: m.role, content: m.content })),
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Something went wrong.");
      setMessages((prev) => [...prev, { role: "assistant", content: data.reply }]);
      setStatus(data.status);
      if (data.status?.setupComplete) {
        onSetupComplete?.();
      }
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
    <div className="bg-white border border-indigo-200 rounded-2xl shadow-sm overflow-hidden">
      <div className="bg-gradient-to-r from-indigo-600 to-fuchsia-600 px-5 py-3 flex items-center gap-2">
        <Sparkles size={18} className="text-white" />
        <h3 className="text-sm font-semibold text-white">Let's get you set up</h3>
      </div>

      <div className="flex items-center gap-4 px-5 py-2.5 bg-indigo-50/60 border-b border-indigo-100 text-xs">
        <span className="flex items-center gap-1.5">
          {status?.propertyCount > 0 ? <CheckCircle2 size={14} className="text-emerald-600" /> : <Circle size={14} className="text-slate-300" />}
          <span className={status?.propertyCount > 0 ? "text-emerald-700 font-medium" : "text-slate-500"}>Add a property</span>
        </span>
        <span className="flex items-center gap-1.5">
          {status?.leaseCount > 0 ? <CheckCircle2 size={14} className="text-emerald-600" /> : <Circle size={14} className="text-slate-300" />}
          <span className={status?.leaseCount > 0 ? "text-emerald-700 font-medium" : "text-slate-500"}>Add a lease</span>
        </span>
        <span className="flex items-center gap-1.5">
          {status?.billingPlan && status.billingPlan !== "trial" ? <CheckCircle2 size={14} className="text-emerald-600" /> : <Circle size={14} className="text-slate-300" />}
          <span className="text-slate-500">Subscribe to a plan</span>
        </span>
      </div>

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
          placeholder="Tell me about your first property…"
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
    </div>
  );
}
