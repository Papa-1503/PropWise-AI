import { useState, useEffect } from "react";
import { useAuth } from "./AuthContext";
import { API_BASE } from "./config";
import { FileText, Wrench, DollarSign, Image, Sparkles, X } from "lucide-react";

/**
 * WelcomeScreen
 *
 * A tenant's first-login welcome — the genuine remaining gap from the
 * "tenant onboarding flow" idea, after checking what already existed:
 * account setup itself (step 3) was already fully built via the
 * invite-code system, and a rent-due-dates view (step 2) already
 * existed in the Payments tab. This covers what didn't exist —
 * a real welcome moment combining actual lease details, a quick
 * portal orientation, and a pointer to the AI assistant.
 *
 * Shown once, persisted via localStorage, same pattern as the staff
 * OnboardingTour — deliberately simpler (a single screen, not a
 * multi-step tour), since the tenant portal is only 5 tabs.
 */

const STORAGE_KEY = "rentflow_tenant_welcome_seen";

const TABS_INTRO = [
  { icon: FileText, label: "Documents", desc: "Your lease and other paperwork" },
  { icon: Wrench, label: "Maintenance", desc: "Report an issue anytime" },
  { icon: DollarSign, label: "Payments", desc: "See what's due and your payment history" },
  { icon: Image, label: "Gallery", desc: "Photos of the property and amenities" },
  { icon: Sparkles, label: "AI", desc: "Ask questions about your rent, due dates, or policies" },
];

export default function WelcomeScreen({ userName }) {
  const [dismissed, setDismissed] = useState(() => {
    try {
      return localStorage.getItem(STORAGE_KEY) === "true";
    } catch {
      return false;
    }
  });
  const [lease, setLease] = useState(null);
  const [loading, setLoading] = useState(true);
  const { authFetch } = useAuth();

  useEffect(() => {
    if (dismissed) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await authFetch(`${API_BASE}/leases/mine`);
        if (res.ok && !cancelled) {
          const data = await res.json();
          setLease(data.lease);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [dismissed, authFetch]);

  function dismiss() {
    setDismissed(true);
    try {
      localStorage.setItem(STORAGE_KEY, "true");
    } catch {
      // persistence is a nicety here, not required for this session
    }
  }

  if (dismissed || loading) return null;

  return (
    <div className="fixed inset-0 z-[130] bg-slate-900/60 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md overflow-hidden">
        <div className="bg-gradient-to-r from-indigo-600 via-violet-600 to-fuchsia-600 text-white px-6 py-5 relative">
          <button onClick={dismiss} className="absolute top-3 right-3 text-white/70 hover:text-white">
            <X size={18} />
          </button>
          <h2 className="text-lg font-serif font-bold">Welcome{userName ? `, ${userName}` : ""}!</h2>
          <p className="text-sm text-white/80 mt-1">Your resident account is all set up.</p>
        </div>

        {lease && (
          <div className="px-6 py-4 border-b border-slate-100 bg-slate-50">
            <p className="text-xs text-slate-500">Unit {lease.unitId}</p>
            {lease.rent > 0 && (
              <p className="text-lg font-semibold text-slate-800">${lease.rent.toLocaleString()}<span className="text-sm font-normal text-slate-500">/month</span></p>
            )}
            {lease.endDate && (
              <p className="text-xs text-slate-500 mt-0.5">
                Lease through {new Date(lease.endDate).toLocaleDateString()}
              </p>
            )}
          </div>
        )}

        <div className="px-6 py-4 space-y-3">
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide">What's in your portal</p>
          {TABS_INTRO.map((t) => (
            <div key={t.label} className="flex items-start gap-3">
              <t.icon size={16} className="text-indigo-500 mt-0.5 shrink-0" />
              <div>
                <p className="text-sm font-medium text-slate-800">{t.label}</p>
                <p className="text-xs text-slate-500">{t.desc}</p>
              </div>
            </div>
          ))}
        </div>

        <div className="px-6 pb-5">
          <button
            onClick={dismiss}
            className="w-full text-sm font-semibold bg-slate-900 text-white py-2.5 rounded-lg"
          >
            Get started
          </button>
        </div>
      </div>
    </div>
  );
}
