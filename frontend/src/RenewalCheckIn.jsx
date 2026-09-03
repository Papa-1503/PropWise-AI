import { useState } from "react";
import { useParams } from "react-router-dom";
import { MessageSquareHeart } from "lucide-react";
import { useAuth } from "./AuthContext";
import { API_BASE } from "./config";

/**
 * RenewalCheckIn — the real "capture why, not just predict that" page
 * a resident lands on from the check-in notification sent by
 * backend/routers/admin.py's _do_renewal_risk_check. A small,
 * standalone route (not folded into a tenant "Leases" tab, since none
 * exists — tenants don't have a dedicated leases page in this app at
 * all, confirmed directly) reachable by any authenticated user via
 * /app/renewal-checkin/:leaseId.
 */
export default function RenewalCheckIn() {
  const { leaseId } = useParams();
  const { authFetch } = useAuth();
  const [response, setResponse] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!response.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await authFetch(`${API_BASE}/leases/${leaseId}/renewal-checkin`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ response: response.trim() }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Couldn't submit your response — please try again.");
      setSubmitted(true);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  if (submitted) {
    return (
      <div className="max-w-lg mx-auto p-6 text-center">
        <MessageSquareHeart size={32} className="mx-auto text-indigo-600 mb-3" />
        <h1 className="text-lg font-semibold mb-1">Thank you for letting us know</h1>
        <p className="text-sm text-slate-500">Your response has been shared with the property team.</p>
      </div>
    );
  }

  return (
    <div className="max-w-lg mx-auto p-6">
      <h1 className="text-lg font-semibold mb-1">How are you feeling about renewing?</h1>
      <p className="text-sm text-slate-500 mb-4">
        We'd genuinely like to know — anything we could do better, any concerns about renewing, or anything else you'd like us to know.
      </p>
      <form onSubmit={handleSubmit} className="bg-white border border-slate-200 rounded-xl p-5">
        <textarea
          value={response}
          onChange={(e) => setResponse(e.target.value)}
          rows={5}
          placeholder="Share as much or as little as you'd like…"
          className="w-full text-sm border border-slate-200 rounded-md px-3 py-2 mb-3"
        />
        {error && <p className="text-xs text-rose-600 bg-rose-50 border border-rose-200 rounded px-3 py-2 mb-3">{error}</p>}
        <button
          type="submit"
          disabled={submitting || !response.trim()}
          className="w-full bg-indigo-600 hover:bg-indigo-700 disabled:bg-slate-300 text-white text-sm font-semibold py-2.5 rounded-lg"
        >
          {submitting ? "Sending…" : "Send"}
        </button>
      </form>
    </div>
  );
}
