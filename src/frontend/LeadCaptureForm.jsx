import { useState } from "react";
import { API_BASE } from "./config";

/**
 * Public lead-capture form — no login required. Visit /apply on the site
 * to see this instead of the login screen. Submits to POST /api/leads,
 * which feeds the LeasingAI numbers on the staff Dashboard.
 */
export default function LeadCaptureForm() {
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
        body: JSON.stringify(form),
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
      <div className="min-h-screen app-bg flex items-center justify-center">
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
    <div className="min-h-screen app-bg flex items-center justify-center">
      <form
        onSubmit={handleSubmit}
        className="bg-white border border-slate-200 rounded-xl p-9 w-[360px] shadow-sm"
      >
        <h1 className="text-xl font-serif font-bold mb-1 text-center">Interested in a unit?</h1>
        <p className="text-xs text-slate-500 mb-5 text-center">Tell us a bit about what you're looking for.</p>

        <input
          type="text" required placeholder="Full name" value={form.name}
          onChange={(e) => update("name", e.target.value)}
          className="w-full text-sm border border-slate-200 rounded-md px-3 py-2 mb-2"
        />
        <input
          type="email" required placeholder="Email" value={form.email}
          onChange={(e) => update("email", e.target.value)}
          className="w-full text-sm border border-slate-200 rounded-md px-3 py-2 mb-2"
        />
        <input
          type="tel" placeholder="Phone (optional)" value={form.phone}
          onChange={(e) => update("phone", e.target.value)}
          className="w-full text-sm border border-slate-200 rounded-md px-3 py-2 mb-2"
        />
        <input
          type="text" placeholder="Unit of interest (optional)" value={form.unitId}
          onChange={(e) => update("unitId", e.target.value)}
          className="w-full text-sm border border-slate-200 rounded-md px-3 py-2 mb-2"
        />
        <textarea
          placeholder="Anything else we should know? (optional)" value={form.message}
          onChange={(e) => update("message", e.target.value)}
          rows={3}
          className="w-full text-sm border border-slate-200 rounded-md px-3 py-2 mb-2"
        />

        {error && (
          <p className="text-xs text-rose-600 bg-rose-50 border border-rose-200 rounded px-3 py-2 mt-1 mb-2">
            {error}
          </p>
        )}

        <button
          type="submit" disabled={submitting}
          className="w-full mt-2 bg-amber-500 disabled:bg-slate-300 text-white text-sm font-semibold py-2.5 rounded-lg hover:bg-amber-600"
        >
          {submitting ? "Submitting…" : "Submit"}
        </button>
      </form>
    </div>
  );
}
value={form.message}
          onChange={(e) => update("message", e.target.value)}
          rows={3}
          className="w-full text-sm border border-slate-200 rounded-md px-3 py-2 mb-2"
        />

        {error && (
          <p className="text-xs text-rose-600 bg-rose-50 border border-rose-200 rounded px-3 py-2 mt-1 mb-2">
            {error}
          </p>
        )}

        <button
          type="submit" disabled={submitting}
          className="w-full mt-2 bg-amber-500 disabled:bg-slate-300 text-white text-sm font-semibold py-2.5 rounded-lg hover:bg-amber-600"
        >
          {submitting ? "Submitting…" : "Submit"}
        </button>
      </form>
    </div>
  );
}
