import { useState, useEffect, useCallback } from "react";
import { FileText, Download, PenLine } from "lucide-react";
import { useAuth } from "./AuthContext";
import { API_BASE } from "./config";
import EmptyState from "./EmptyState";

/**
 * Documents — staff can create a document for a tenant (title + content);
 * the tenant can view, e-sign (typed name, timestamped), and download a
 * PDF. See routers/documents.py for the legal-content caveat: this app
 * does not generate lease language, only the workflow around it.
 *
 * CHANGED (Sept 3, 2026): added the real lease picker this form never
 * had — confirmed the previous version never collected leaseId at all,
 * so a document had nothing to resolve a building name from even after
 * the backend was fixed to display one. Picking a lease also auto-fills
 * tenantEmail from that lease's own residentEmail, real by-product
 * value beyond just fixing the missing building name (removes a real
 * source of typos: a hand-typed email that doesn't match the actual
 * resident on file).
 */
export default function Documents() {
  const { user, authFetch } = useAuth();
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ tenantEmail: "", title: "", content: "", leaseId: "" });
  const [creating, setCreating] = useState(false);

  const [leaseOptions, setLeaseOptions] = useState([]);
  const [leasesLoaded, setLeasesLoaded] = useState(false);

  const [signingId, setSigningId] = useState(null);
  const [signName, setSignName] = useState("");
  const [signing, setSigning] = useState(false);

  const fetchDocuments = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await authFetch(`${API_BASE}/documents`);
      if (!res.ok) throw new Error("Couldn't load documents.");
      const data = await res.json();
      setDocuments(data.documents || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [authFetch]);

  useEffect(() => {
    fetchDocuments();
  }, [fetchDocuments]);

  // Loaded once, lazily, the first time staff actually opens the create
  // form — no need to pay for two extra requests (leases + properties)
  // on every visit to this page when most visits are just reviewing
  // existing documents, not creating a new one.
  const loadLeaseOptions = useCallback(async () => {
    if (leasesLoaded) return;
    try {
      const [leasesRes, propertiesRes] = await Promise.all([
        authFetch(`${API_BASE}/leases`),
        authFetch(`${API_BASE}/properties`),
      ]);
      const leasesData = leasesRes.ok ? await leasesRes.json() : { leases: [] };
      const propertiesData = propertiesRes.ok ? await propertiesRes.json() : { properties: [] };
      const propertyNameById = {};
      for (const p of propertiesData.properties || []) propertyNameById[p.id] = p.name;
      const options = (leasesData.leases || []).map((l) => ({
        id: l.id,
        residentEmail: l.residentEmail || "",
        label: `${propertyNameById[l.propertyId] || "Unknown building"} — Unit ${l.unitId}${l.residentName ? ` (${l.residentName})` : ""}`,
      }));
      setLeaseOptions(options);
      setLeasesLoaded(true);
    } catch {
      setLeaseOptions([]);
    }
  }, [authFetch, leasesLoaded]);

  function toggleCreateForm() {
    setShowCreate((v) => {
      const next = !v;
      if (next) loadLeaseOptions();
      return next;
    });
  }

  function handleLeaseChange(leaseId) {
    const selected = leaseOptions.find((l) => l.id === leaseId);
    setForm((f) => ({
      ...f,
      leaseId,
      // Only auto-fill if the field's still empty or matches the
      // previously-selected lease's email — never clobber an email
      // staff already deliberately typed by hand.
      tenantEmail: selected?.residentEmail && (!f.tenantEmail || leaseOptions.some((l) => l.residentEmail === f.tenantEmail))
        ? selected.residentEmail
        : f.tenantEmail,
    }));
  }

  async function handleCreate(e) {
    e.preventDefault();
    setCreating(true);
    try {
      const payload = { ...form };
      if (!payload.leaseId) delete payload.leaseId; // omit entirely rather than send an empty string the backend would reject as an invalid ObjectId
      const res = await authFetch(`${API_BASE}/documents`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error("Couldn't create document.");
      setForm({ tenantEmail: "", title: "", content: "", leaseId: "" });
      setShowCreate(false);
      fetchDocuments();
    } catch (err) {
      setError(err.message);
    } finally {
      setCreating(false);
    }
  }

  async function handleSign(docId) {
    setSigning(true);
    try {
      const res = await authFetch(`${API_BASE}/documents/${docId}/sign`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ signedByName: signName }),
      });
      if (!res.ok) throw new Error("Couldn't sign document.");
      setSigningId(null);
      setSignName("");
      fetchDocuments();
    } catch (err) {
      setError(err.message);
    } finally {
      setSigning(false);
    }
  }

  function downloadPdf(docId) {
    authFetch(`${API_BASE}/documents/${docId}/pdf`)
      .then((res) => res.blob())
      .then((blob) => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `document_${docId}.pdf`;
        a.click();
        URL.revokeObjectURL(url);
      });
  }

  return (
    <div className="p-5">
      <div className="flex items-center justify-between mb-1">
        <h1 className="text-2xl font-semibold">Documents</h1>
        {user.role === "staff" && (
          <button
            onClick={toggleCreateForm}
            className="text-sm bg-amber-500 hover:bg-amber-600 text-white font-semibold px-4 py-2 rounded-lg"
          >
            + New Document
          </button>
        )}
      </div>
      <p className="text-sm text-slate-500 mb-5">
        {user.role === "staff" ? "Agreements and forms sent to tenants." : "Your agreements and forms."}
      </p>

      {showCreate && (
        <form onSubmit={handleCreate} className="bg-white border border-slate-200 rounded-xl p-5 mb-5 space-y-2">
          <select
            value={form.leaseId}
            onChange={(e) => handleLeaseChange(e.target.value)}
            className="w-full text-sm border border-slate-200 rounded-md px-3 py-2 bg-white"
          >
            <option value="">No lease selected — building name won't show on this document</option>
            {leaseOptions.map((l) => (
              <option key={l.id} value={l.id}>{l.label}</option>
            ))}
          </select>
          <input
            type="email" required placeholder="Tenant email" value={form.tenantEmail}
            onChange={(e) => setForm((f) => ({ ...f, tenantEmail: e.target.value }))}
            className="w-full text-sm border border-slate-200 rounded-md px-3 py-2"
          />
          <input
            type="text" required placeholder="Document title" value={form.title}
            onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
            className="w-full text-sm border border-slate-200 rounded-md px-3 py-2"
          />
          <textarea
            required placeholder="Document content" value={form.content} rows={6}
            onChange={(e) => setForm((f) => ({ ...f, content: e.target.value }))}
            className="w-full text-sm border border-slate-200 rounded-md px-3 py-2"
          />
          <button
            type="submit" disabled={creating}
            className="bg-slate-900 text-white text-sm font-semibold px-4 py-2 rounded-lg disabled:bg-slate-300"
          >
            {creating ? "Creating…" : "Create & Send"}
          </button>
        </form>
      )}

      {error && <p className="text-sm text-rose-600 bg-rose-50 border border-rose-200 rounded px-3 py-2 mb-3">{error}</p>}

      {loading ? (
        <p className="text-sm text-slate-400">Loading…</p>
      ) : documents.length === 0 ? (
        <EmptyState icon={FileText} title="No documents yet" />
      ) : (
        <div className="space-y-3">
          {documents.map((doc) => (
            <div key={doc._id} className="bg-white border border-slate-200 rounded-xl p-4">
              <div className="flex items-center justify-between">
                <div>
                  {doc.buildingName && (
                    <p className="text-xs font-medium text-slate-500 mb-0.5">{doc.buildingName}</p>
                  )}
                  <p className="font-semibold text-sm">{doc.title}</p>
                  <p className="text-xs text-slate-400">
                    {doc.status === "signed"
                      ? `Signed by ${doc.signedByName} on ${new Date(doc.signedAt).toLocaleDateString()}`
                      : "Awaiting signature"}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => downloadPdf(doc._id)}
                    className="text-xs flex items-center gap-1 border border-slate-200 rounded-full px-3 py-1.5 hover:bg-slate-50"
                  >
                    <Download size={13} /> PDF
                  </button>
                  {user.role === "tenant" && doc.status !== "signed" && (
                    <button
                      onClick={() => setSigningId(signingId === doc._id ? null : doc._id)}
                      className="text-xs flex items-center gap-1 bg-amber-500 hover:bg-amber-600 text-white rounded-full px-3 py-1.5"
                    >
                      <PenLine size={13} /> Sign
                    </button>
                  )}
                </div>
              </div>

              {signingId === doc._id && (
                <div className="mt-3 pt-3 border-t border-slate-100 flex items-center gap-2">
                  <input
                    type="text" placeholder="Type your full legal name" value={signName}
                    onChange={(e) => setSignName(e.target.value)}
                    className="flex-1 text-sm border border-slate-200 rounded-md px-3 py-2"
                  />
                  <button
                    onClick={() => handleSign(doc._id)}
                    disabled={!signName || signing}
                    className="text-sm bg-slate-900 disabled:bg-slate-300 text-white font-semibold px-4 py-2 rounded-lg"
                  >
                    {signing ? "Signing…" : "Confirm Signature"}
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
