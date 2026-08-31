import { useState, useEffect, useCallback } from "react";
import { useAuth } from "./AuthContext";
import { PenTool, Copy, Check } from "lucide-react";
import { API_BASE } from "./config";

export default function WriteAssist({ propertyId }) {
  const [instruction, setInstruction] = useState("");
  const [channel, setChannel] = useState("email");
  const [leaseId, setLeaseId] = useState("");
  const [leases, setLeases] = useState([]);
  const [draft, setDraft] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [copied, setCopied] = useState(false);
  const { authFetch } = useAuth();

  const fetchLeases = useCallback(async () => {
    const params = new URLSearchParams();
    if (propertyId) params.set("propertyId", propertyId);
    const res = await authFetch(`${API_BASE}/leases?${params.toString()}`);
    if (res.ok) {
      const data = await res.json();
      setLeases(data.leases || []);
    }
  }, [propertyId, authFetch]);

  useEffect(() => {
    fetchLeases();
  }, [fetchLeases]);

  async function handleDraft() {
    setLoading(true);
    setError(null);
    setDraft(null);
    try {
      const res = await authFetch(`${API_BASE}/write-assist/draft`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ instruction, channel, leaseId: leaseId || null }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Couldn't generate a draft.");
      setDraft(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  function handleCopy() {
    navigator.clipboard?.writeText(draft.draft);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <div className="max-w-2xl mx-auto">
      <div className="flex items-center gap-2 mb-3">
        <PenTool size={18} className="text-indigo-600" />
        <h2 className="text-lg font-semibold">Write with AI</h2>
      </div>

      <div className="bg-white border border-slate-200 rounded-xl p-4 space-y-3">
        <textarea
          value={instruction}
          onChange={(e) => setInstruction(e.target.value)}
          placeholder="Tell the AI what to say, e.g. 'tell them their lease renews in 60 days and offer a tour'"
          rows={3}
          className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
        />

        <div className="grid grid-cols-2 gap-3">
          <select
            value={channel}
            onChange={(e) => setChannel(e.target.value)}
            className="border border-slate-200 rounded-lg px-3 py-2 text-sm"
          >
            <option value="email">Email</option>
            <option value="sms">Text (SMS)</option>
          </select>
          <select
            value={leaseId}
            onChange={(e) => setLeaseId(e.target.value)}
            className="border border-slate-200 rounded-lg px-3 py-2 text-sm"
          >
            <option value="">No specific resident (generic)</option>
            {leases.map((l) => (
              <option key={l.id} value={l.id}>{l.residentName} — Unit {l.unitId}</option>
            ))}
          </select>
        </div>

        {error && <p className="text-sm text-rose-600" role="alert">{error}</p>}

        <button
          onClick={handleDraft}
          disabled={!instruction || loading}
          className="w-full bg-slate-900 text-white rounded-lg py-2 text-sm font-semibold hover:bg-slate-800 disabled:opacity-50"
        >
          {loading ? "Drafting..." : "Draft it"}
        </button>
      </div>

      {draft && (
        <div className="bg-white border border-slate-200 rounded-xl p-4 mt-3">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-semibold">
              Draft {draft.groundedInLease ? "— grounded in the selected lease" : "— generic (no lease selected)"}
            </h3>
            <button onClick={handleCopy} className="flex items-center gap-1 text-xs font-medium text-indigo-600 hover:underline">
              {copied ? <Check size={13} /> : <Copy size={13} />}
              {copied ? "Copied" : "Copy"}
            </button>
          </div>
          <pre className="text-sm text-slate-700 whitespace-pre-wrap font-sans bg-slate-50 rounded-lg p-3">{draft.draft}</pre>
          <p className="text-xs text-slate-400 mt-2">Review before sending — this is a draft, not sent automatically.</p>
        </div>
      )}
    </div>
  );
}
