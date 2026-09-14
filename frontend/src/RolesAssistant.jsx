import { useState, useEffect, useRef } from "react";
import { Sparkles, Send, ChevronDown, ChevronUp } from "lucide-react";
import { useAuth } from "./AuthContext";
import { API_BASE } from "./config";

/**
 * RolesAssistant
 *
 * Real, conversational roles-setup guide for backend
 * routers/roles_assistant.py - the seventh feature built on the same
 * real agentic tool-calling pattern (see OnboardingAssistant.jsx and
 * the other five assistants). Helps a new organization think through
 * what real roles their team needs (e.g. "Leasing Agent" -> leasing +
 * communications) and create/assign them, reusing the exact real
 * create_custom_role and assign_custom_role logic already proven in
 * the manual UI on this page.
 *
 * Collapsible, and hides itself once every staff member has a real
 * role assignment decision made (a real "done" state) - reappears
 * automatically if a new staff member without a role assignment
 * shows up.
 */
export default function RolesAssistant({ onChanged }) {
  const { authFetch } = useAuth();
  const [expanded, setExpanded] = useState(false);
  const [unassignedCount, setUnassignedCount] = useState(null);
  const [messages, setMessages] = useState([
    { role: "assistant", content: "Hi! Want help setting up roles for your team? Tell me about the different jobs your staff do." },
  ]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const scrollRef = useRef(null);

  useEffect(() => {
    authFetch(`${API_BASE}/roles-assistant/status`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => data && setUnassignedCount(data.unassignedStaffCount))
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
      const res = await authFetch(`${API_BASE}/roles-assistant/chat`, {
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
      setUnassignedCount(data.unassignedStaffCount);
      onChanged?.();
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

  if (unassignedCount === 0) return null; // everyone already has a real role decision made

  return (
    <div className="bg-white border border-indigo-200 rounded-2xl shadow-sm overflow-hidden mb-3">
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full bg-gradient-to-r from-indigo-600 to-fuchsia-600 px-5 py-3 flex items-center justify-between gap-2"
      >
        <span className="flex items-center gap-2">
          <Sparkles size={18} className="text-white" />
          <h3 className="text-sm font-semibold text-white">
            Set up roles with AI{unassignedCount != null ? ` — ${unassignedCount} unassigned` : ""}
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
              placeholder="e.g. We have leasing agents and maintenance techs"
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
