import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { API_BASE } from "./config";
import ProspectChatWidget from "./ProspectChatWidget";

/**
 * LeadCaptureForm — the public /apply page.
 *
 * CHANGED (Sept 3, 2026): added the real 24/7 leasing assistant
 * (ProspectChatWidget) as the primary interface, with this form kept
 * as the explicit "just leave your info" fallback for anyone who'd
 * rather not chat, or who wants a human to follow up regardless of
 * what the assistant already answered. Optional ?property=<id> query
 * param scopes the assistant to one building — omitted, it answers
 * across every currently vacant unit in the whole portfolio.
 */
export default function LeadCaptureForm() {
  const [searchParams] = useSearchParams();
  const propertyId = searchParams.get("property") || null;

  const [form, setForm] = useState({ name: "", email: "", phone: "", unitId: "", message: "" });
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  function update(field, value) {
    setForm((f) => ({ ...f, [field]: value }));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/leads`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...form, propertyId: propertyId || undefined }),
      });
      if (!res.ok) throw new Error("Something went wrong submitting your info. Please try again.");
      setSubmitted(true);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  if (submitted) {
    return (
      <div className="min-h-screen app-bg flex items-center justify-center p-4">
        <div className="bg-white border border-slate-200 rounded-xl p-9 w-[360px] text-center shadow-sm">
          <h1 className="text-xl font-serif font-bold mb-2">Thanks for reaching out!</h1>
          <p className="text-sm text-slate-500">
            We've received your info and someone from our team will be in touch soon.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen app-bg flex items-center justify-center p-4">
      <div className="w-full max-w-3xl grid grid-cols-1 lg:grid-cols-2 gap-5 items-start">
        <div>
          <h1 className="text-xl font-serif font-bold mb-1 text-white text-center lg:text-left">Looking for a place to live?</h1>
          <p className="text-xs text-slate-200 mb-3 text-center lg:text-left">
            Ask our assistant anything about current availability, or leave your info and we'll reach out.
          </p>
          <ProspectChatWidget propertyId={propertyId} />
        </div>

        <form onSubmit={handleSubmit} className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm">
          <h2 className="text-base font-semibold mb-1 text-center lg:text-left">Prefer we contact you?</h2>
          <p className="text-xs text-slate-500 mb-4 text-center lg:text-left">Leave your info and someone will follow up.</p>
          <input type="text" required placeholder="Full name" value={form.name} onChange={(e) => update("name", e.target.value)} className="w-full text-sm border border-slate-200 rounded-md px-3 py-2 mb-2" />
          <input type="email" required placeholder="Email" value={form.email} onChange={(e) => update("email", e.target.value)} className="w-full text-sm border border-slate-200 rounded-md px-3 py-2 mb-2" />
          <input type="tel" placeholder="Phone (optional)" value={form.phone} onChange={(e) => update("phone", e.target.value)} className="w-full text-sm border border-slate-200 rounded-md px-3 py-2 mb-2" />
          <input type="text" placeholder="Unit of interest (optional)" value={form.unitId} onChange={(e) => update("unitId", e.target.value)} className="w-full text-sm border border-slate-200 rounded-md px-3 py-2 mb-2" />
          <textarea placeholder="Anything else we should know? (optional)" value={form.message} onChange={(e) => update("message", e.target.value)} rows={3} className="w-full text-sm border border-slate-200 rounded-md px-3 py-2 mb-2" />
          {error && <p className="text-xs text-rose-600 bg-rose-50 border border-rose-200 rounded px-3 py-2 mt-1 mb-2">{error}</p>}
          <button type="submit" disabled={submitting} className="w-full mt-2 bg-amber-500 disabled:bg-slate-300 text-white text-sm font-semibold py-2.5 rounded-lg hover:bg-amber-600">
            {submitting ? "Submitting…" : "Submit"}
          </button>
        </form>
      </div>
    </div>
  );
}
