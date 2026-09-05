import { useState, useId } from "react";
import { useAuth } from "./AuthContext";

/**
 * LoginScreen
 *
 * Real staff/resident login — calls POST /api/auth/login and stores a
 * real JWT via AuthContext. Role is determined by the account itself
 * (returned from the backend), not chosen client-side.
 *
 * CHANGED Aug 25, 2026 (Priority 34): sign-up now uses a single invite
 * code instead of raw "Property ID"/"Unit ID" fields — both a real
 * security fix (the backend no longer trusts any client-submitted
 * propertyId/unitId at all for this path) and the fix for a UX gap two
 * external audits both flagged independently. Staff generate an invite
 * code when creating a lease (Leases tab); a resident enters that code
 * here to activate their account, already bound to the correct unit.
 * New staff accounts are still provisioned by an existing staff member,
 * not through this public form.
 *
 * CHANGED Aug 25, 2026 (Priority 36 — accessibility): added real
 * <label> elements (previously placeholder-only), autocomplete
 * attributes, a proper tablist/tab/aria-selected pattern for the
 * Sign In / Activate toggle (already visually a tab switcher, now
 * semantically one too), aria-live on the error message, and fixed
 * two contrast failures found by an external audit — computed exactly
 * with the real WCAG formula, not eyeballed: the amber button's white
 * text measured 2.15:1 (audit reported ~2.14:1, matching), now amber-700
 * for 5.02:1; the inactive tab text measured 4.34:1 (exact match to the
 * audit), now slate-600 for 6.92:1. Both clear the 4.5:1 AA threshold
 * with real margin.
 *
 * CHANGED Sept 1, 2026: background swapped to an animated Minneapolis
 * night skyline (login-skyline-bg, see index.css) — a deliberate,
 * site-specific "arriving at the door" moment rather than the plain
 * dot-grid app-bg used everywhere else. Form card itself untouched
 * apart from a deeper shadow (shadow-sm -> shadow-lg) to lift it off
 * the busier background — none of the accessibility fixes above were
 * touched, since the card remains solid white regardless of what's
 * behind it.
 */
export default function LoginScreen() {
  const { login, register } = useAuth();
  const [mode, setMode] = useState("signin"); // "signin" | "signup"
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [inviteCode, setInviteCode] = useState("");
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const idPrefix = useId();

  async function handleSubmit(e) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      if (mode === "signin") {
        await login(email, password);
      } else {
        await register({ email, password, name, inviteCode });
      }
    } catch (err) {
      setError(err.message || "Something went wrong.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center login-skyline-bg px-4">
      <form
        onSubmit={handleSubmit}
        className="bg-white border border-slate-200 rounded-xl p-9 w-full max-w-[340px] text-center shadow-lg"
      >
        <h1 className="text-2xl font-serif font-bold mb-1">PropWise AI</h1>
        <p className="text-xs text-slate-500 mb-5">Property operations &amp; resident tools</p>

        <div role="tablist" aria-label="Sign in or activate account" className="flex bg-slate-100 rounded-lg p-1 mb-4 text-xs font-semibold">
          <button
            type="button"
            role="tab"
            aria-selected={mode === "signin"}
            onClick={() => { setMode("signin"); setError(null); }}
            className={`flex-1 py-1.5 rounded-md ${mode === "signin" ? "bg-white shadow-sm" : "text-slate-600"}`}
          >
            Sign In
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={mode === "signup"}
            onClick={() => { setMode("signup"); setError(null); }}
            className={`flex-1 py-1.5 rounded-md ${mode === "signup" ? "bg-white shadow-sm" : "text-slate-600"}`}
          >
            Activate Resident Account
          </button>
        </div>

        {mode === "signup" && (
          <div className="text-left mb-2">
            <label htmlFor={`${idPrefix}-name`} className="sr-only">Full name</label>
            <input
              id={`${idPrefix}-name`}
              type="text"
              required
              autoComplete="name"
              placeholder="Full name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full text-sm border border-slate-200 rounded-md px-3 py-2"
            />
          </div>
        )}

        <div className="text-left mb-2">
          <label htmlFor={`${idPrefix}-email`} className="sr-only">Email</label>
          <input
            id={`${idPrefix}-email`}
            type="email"
            required
            autoComplete="email"
            placeholder="Email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full text-sm border border-slate-200 rounded-md px-3 py-2"
          />
        </div>
        <div className="text-left mb-2">
          <label htmlFor={`${idPrefix}-password`} className="sr-only">Password</label>
          <input
            id={`${idPrefix}-password`}
            type="password"
            required
            autoComplete={mode === "signin" ? "current-password" : "new-password"}
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full text-sm border border-slate-200 rounded-md px-3 py-2"
          />
        </div>

        {mode === "signup" && (
          <>
            <div className="text-left mb-2">
              <label htmlFor={`${idPrefix}-invite`} className="sr-only">Invite code</label>
              <input
                id={`${idPrefix}-invite`}
                type="text"
                required
                autoComplete="off"
                placeholder="Invite code"
                value={inviteCode}
                onChange={(e) => setInviteCode(e.target.value.toUpperCase())}
                className="w-full text-sm border border-slate-200 rounded-md px-3 py-2 tracking-widest text-center font-mono"
              />
            </div>
            <p className="text-[10px] text-slate-400 mb-2 text-left">
              Get your invite code from your property manager — it links your account to your unit.
            </p>
          </>
        )}

        {error && (
          <p role="alert" aria-live="polite" className="text-xs text-rose-600 bg-rose-50 border border-rose-200 rounded px-3 py-2 mt-2 text-left">
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={submitting}
          className="w-full mt-3 bg-amber-700 disabled:bg-slate-300 text-white text-sm font-semibold py-2.5 rounded-lg hover:bg-amber-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-900"
        >
          {submitting
            ? mode === "signin" ? "Signing in…" : "Activating…"
            : mode === "signin" ? "Sign in" : "Activate account"}
        </button>

        <p className="text-[11px] text-slate-400 mt-4 text-center">
          Property manager? <a href="/signup" className="text-indigo-600 underline">Create your organization</a>
        </p>
      </form>
    </div>
  );
}
