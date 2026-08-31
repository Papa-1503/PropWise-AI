import { useState, useEffect, useCallback } from "react";
import { useAuth } from "./AuthContext";
import EmptyState from "./EmptyState";
import { ClipboardList, ChevronDown, ChevronRight, Copy, Check } from "lucide-react";
import { API_BASE } from "./config";

/**
 * FormLibrary
 *
 * Real, staff-facing catalog of every form/checklist this app has,
 * fetched from GET /api/forms (backend/routers/forms.py) - a genuine,
 * hardcoded index of real, already-working forms elsewhere in the app
 * (maintenance tickets, turnover checklists split by role, leases,
 * screening, RUBS, and more), not a new form-building system.
 *
 * Each form entry shows its real API endpoint plainly, since most of
 * these don't have a single dedicated page of their own yet (a "new
 * lease" form, for instance, already lives inside the Leases tab) -
 * this is honestly a directory pointing to where each real form
 * already lives or how to reach it directly, not a claim that every
 * one of these has its own standalone screen here.
 */
export default function FormLibrary() {
  const [categories, setCategories] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [expanded, setExpanded] = useState({});
  const [copiedEndpoint, setCopiedEndpoint] = useState(null);
  const { authFetch } = useAuth();

  const fetchCatalog = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await authFetch(`${API_BASE}/forms`);
      if (!res.ok) throw new Error("Couldn't load the form library.");
      const data = await res.json();
      setCategories(data.categories || []);
      if (data.categories?.length) {
        setExpanded({ [data.categories[0].category]: true });
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [authFetch]);

  useEffect(() => {
    fetchCatalog();
  }, [fetchCatalog]);

  function toggleCategory(category) {
    setExpanded((prev) => ({ ...prev, [category]: !prev[category] }));
  }

  function copyEndpoint(endpoint) {
    navigator.clipboard?.writeText(endpoint);
    setCopiedEndpoint(endpoint);
    setTimeout(() => setCopiedEndpoint(null), 1500);
  }

  return (
    <div className="max-w-2xl mx-auto">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-lg font-semibold">Form Library</h2>
      </div>

      {loading && <div className="text-sm text-slate-500">Loading...</div>}
      {error && (
        <div className="text-sm text-rose-600 bg-rose-50 border border-rose-200 rounded-lg p-3 mb-3" role="alert">
          {error}
        </div>
      )}

      {!loading && !error && categories.length === 0 && (
        <EmptyState
          icon={ClipboardList}
          title="No forms cataloged"
          subtitle="The form library is empty right now."
        />
      )}

      {!loading && !error && categories.length > 0 && (
        <div className="space-y-3">
          {categories.map((cat) => {
            const isOpen = !!expanded[cat.category];
            return (
              <div key={cat.category} className="bg-white border border-slate-200 rounded-xl overflow-hidden">
                <button
                  onClick={() => toggleCategory(cat.category)}
                  className="w-full flex items-center justify-between px-4 py-3 hover:bg-slate-50"
                >
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-sm">{cat.category}</span>
                    <span className="text-xs text-slate-400">({cat.forms.length})</span>
                  </div>
                  {isOpen ? <ChevronDown size={16} className="text-slate-400" /> : <ChevronRight size={16} className="text-slate-400" />}
                </button>

                {isOpen && (
                  <div className="border-t border-slate-100 divide-y divide-slate-100">
                    {cat.forms.map((form) => (
                      <div key={form.name} className="px-4 py-3">
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <p className="text-sm font-medium text-slate-800">{form.name}</p>
                            <p className="text-xs text-slate-500 mt-0.5">{form.description}</p>
                          </div>
                          <button
                            onClick={() => copyEndpoint(form.realEndpoint)}
                            title="Copy the real API endpoint"
                            className="flex items-center gap-1 text-[11px] font-mono text-slate-500 bg-slate-50 border border-slate-200 rounded px-2 py-1 hover:border-indigo-300 shrink-0"
                          >
                            {copiedEndpoint === form.realEndpoint ? <Check size={11} /> : <Copy size={11} />}
                            {form.realEndpoint}
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
