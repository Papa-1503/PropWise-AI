import { useState, useRef, useEffect } from "react";
import { Send, MessageCircle } from "lucide-react";
import { API_BASE } from "./config";

/**
 * ProspectChatWidget — the real 24/7 leasing assistant, embedded on the
 * public /apply page. No login, no account — a prospect can start
 * asking real questions about vacant units immediately. See
 * backend/routers/prospect_assistant.py for the grounding + mandatory
 * fair housing safeguards behind this.
 *
 * propertyId is optional — omit it to answer across every currently
 * vacant unit in the whole portfolio (the default on a general /apply
 * link), or pass one to scope answers to a single building (e.g. a
 * link specific to one property's own marketing page).
 */
export default function ProspectChatWidget({ propertyId }) {
  const [messages, setMessages] = useState([
    { role: "assistant", content: "Hi! I can answer questions about our currently available units — pricing, availability, pet policy, parking, or help you book a self-guided tour. What would you like to know?" },
  ]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState(null);
  const scrollRef = useRef(null);

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function handleSend(e) {
    e.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || sending) return;

    const nextMessages = [...messages, { role: "user", content: trimmed }];
    setMessages(nextMessages);
    setInput("");
    setSending(true);
    setError(null);

    try {
      const res = await fetch(`${API_BASE}/public/prospect-chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: trimmed,
          propertyId: propertyId || null,
          // Real conversation history, excluding the greeting (that's
          // this widget's own opener, never actually sent to the model
          // as if the assistant said it mid-conversation).
          history: nextMessages.slice(1, -1).map((m) => ({ role: m.role, content: m.content })),
        }),
      });
      if (!res.ok) throw new Error("Something went wrong — please try again, or leave your info below and we'll follow up.");
      const data = await res.json();
      setMessages((prev) => [...prev, { role: "assistant", content: data.answer }]);
    } catch (err) {
      setError(err.message);
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
      <div className="bg-gradient-to-r from-indigo-600 to-fuchsia-600 px-4 py-3 flex items-center gap-2">
        <MessageCircle size={16} className="text-white" />
        <span className="text-white text-sm font-semibold">Ask about our available units</span>
      </div>

      <div className="p-4 space-y-3 max-h-96 overflow-y-auto">
        {messages.map((m, i) => (
          <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
            <div
              className={`max-w-[85%] text-sm rounded-2xl px-3.5 py-2 ${
                m.role === "user"
                  ? "bg-indigo-600 text-white rounded-br-sm"
                  : "bg-slate-100 text-slate-800 rounded-bl-sm"
              }`}
            >
              {m.content}
            </div>
          </div>
        ))}
        {sending && (
          <div className="flex justify-start">
            <div className="bg-slate-100 text-slate-400 text-sm rounded-2xl rounded-bl-sm px-3.5 py-2">
              Typing…
            </div>
          </div>
        )}
        <div ref={scrollRef} />
      </div>

      {error && <p className="text-xs text-rose-600 px-4 pb-2">{error}</p>}

      <form onSubmit={handleSend} className="border-t border-slate-100 p-3 flex items-center gap-2">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask a question…"
          disabled={sending}
          className="flex-1 text-sm border border-slate-200 rounded-full px-3.5 py-2 disabled:bg-slate-50"
        />
        <button
          type="submit"
          disabled={sending || !input.trim()}
          className="shrink-0 bg-indigo-600 hover:bg-indigo-700 disabled:bg-slate-300 text-white rounded-full p-2"
          aria-label="Send"
        >
          <Send size={15} />
        </button>
      </form>
    </div>
  );
}
