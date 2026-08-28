import { useState, useEffect, useRef, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { Search, FileSignature, Wrench, UserPlus2 } from "lucide-react";
import { useAuth } from "./AuthContext";
import { API_BASE } from "./config";

/**
 * Command palette — Ctrl+K (Cmd+K on Mac), modeled on the same shortcut
 * a shared design used, reimplemented against RentFlow's own real
 * data via a genuine backend search (routers/search.py) rather than
 * PropWise's version, which only toggled an empty overlay with no real
 * search behind it. Also fulfils the separate, previously-flagged
 * "global search/command navigation" item from the navigation
 * priorities — one feature satisfying two backlog items.
 */

const TYPE_ICON = { lease: FileSignature, ticket: Wrench, lead: UserPlus2 };

export default function CommandPalette({ propertyId, open, onOpenChange }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const inputRef = useRef(null);
  const navigate = useNavigate();
  const { authFetch, user } = useAuth();

  useEffect(() => {
    function handleKeydown(e) {
      const isK = e.key === "k" || e.key === "K";
      if ((e.metaKey || e.ctrlKey) && isK) {
        e.preventDefault();
        onOpenChange(!open);
      }
      if (e.key === "Escape") onOpenChange(false);
    }
    window.addEventListener("keydown", handleKeydown);
    return () => window.removeEventListener("keydown", handleKeydown);
  }, [open, onOpenChange]);

  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 20);
    else {
      setQuery("");
      setResults([]);
    }
  }, [open]);

  const runSearch = useCallback(async (q) => {
    if (q.trim().length < 2) {
      setResults([]);
      return;
    }
    setLoading(true);
    try {
      const params = new URLSearchParams({ q });
      if (propertyId) params.set("propertyId", propertyId);
      const res = await authFetch(`${API_BASE}/search?${params.toString()}`);
      if (res.ok) {
        const data = await res.json();
        setResults(data.results || []);
      }
    } finally {
      setLoading(false);
    }
  }, [propertyId, authFetch]);

  useEffect(() => {
    const t = setTimeout(() => runSearch(query), 250);
    return () => clearTimeout(t);
  }, [query, runSearch]);

  function goToResult(r) {
    navigate(`/app/${r.navigateTo}`);
    onOpenChange(false);
  }

  if (user?.role !== "staff" || !open) return null;

  return (
    <div className="fixed inset-0 bg-slate-900/50 z-[110] flex items-start justify-center pt-24 px-4" onClick={() => onOpenChange(false)}>
      <div
        className="bg-white rounded-2xl shadow-2xl w-full max-w-lg overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-2.5 px-4 py-3 border-b border-slate-200">
          <Search size={16} className="text-slate-400 shrink-0" />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search leases, tickets, leads…"
            className="flex-1 text-sm outline-none"
          />
          <kbd className="text-[10px] text-slate-400 border border-slate-200 rounded px-1.5 py-0.5">Esc</kbd>
        </div>
        <div className="max-h-80 overflow-y-auto">
          {loading && <p className="text-xs text-slate-400 px-4 py-4">Searching…</p>}
          {!loading && query.trim().length >= 2 && results.length === 0 && (
            <p className="text-xs text-slate-400 px-4 py-4">No matches for "{query}".</p>
          )}
          {!loading && results.map((r) => {
            const Icon = TYPE_ICON[r.type] || Search;
            return (
              <button
                key={`${r.type}-${r.id}`}
                onClick={() => goToResult(r)}
                className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-slate-50 text-left"
              >
                <Icon size={15} className="text-slate-400 shrink-0" />
                <div className="min-w-0">
                  <p className="text-sm text-slate-800 truncate">{r.title}</p>
                  <p className="text-xs text-slate-400 truncate">{r.subtitle}</p>
                </div>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
