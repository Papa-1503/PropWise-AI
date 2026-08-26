import { useState } from "react";
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
    <div className="min-h-screen flex items-center justify-center app-bg px-4">
      <form
        onSubmit={handleSubmit}
        className="bg-white border border-slate-200 rounded-xl p-9 w-full max-w-[340px] text-center shadow-sm"
      >
        <h1 className="text-2xl font-serif font-bold mb-1">RentFlow AI</h1>
        <p className="text-xs text-slate-500 mb-5">Property operations &amp; resident tools</p>

        <div className="flex bg-slate-100 rounded-lg p-1 mb-4 text-xs font-semibold">
          <button
            type="button"
            onClick={() => { setMode("signin"); setError(null); }}
            className={`flex-1 py-1.5 rounded-md ${mode === "signin" ? "bg-white shadow-sm" : "text-slate-500"}`}
          >
            Sign In
          </button>
          <button
            type="button"
            onClick={() => { setMode("signup"); setError(null); }}
            className={`flex-1 py-1.5 rounded-md ${mode === "signup" ? "bg-white shadow-sm" : "text-slate-500"}`}
          >
            Activate Resident Account
          </button>
        </div>

        {mode === "signup" && (
          <input
            type="text"
            required
            placeholder="Full name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="w-full text-sm border border-slate-200 rounded-md px-3 py-2 mb-2"
          />
        )}

        <input
          type="email"
          required
          placeholder="Email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="w-full text-sm border border-slate-200 rounded-md px-3 py-2 mb-2"
        />
        <input
          type="password"
          required
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="w-full text-sm border border-slate-200 rounded-md px-3 py-2 mb-2"
        />

        {mode === "signup" && (
          <>
            <input
              type="text"
              required
              placeholder="Invite code"
              value={inviteCode}
              onChange={(e) => setInviteCode(e.target.value.toUpperCase())}
              className="w-full text-sm border border-slate-200 rounded-md px-3 py-2 mb-2 tracking-widest text-center font-mono"
            />
            <p className="text-[10px] text-slate-400 mb-2 text-left">
              Get your invite code from your property manager — it links your account to your unit.
            </p>
          </>
        )}

        {error && (
          <p className="text-xs text-rose-600 bg-rose-50 border border-rose-200 rounded px-3 py-2 mt-2 text-left">
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={submitting}
          className="w-full mt-3 bg-amber-500 disabled:bg-slate-300 text-white text-sm font-semibold py-2.5 rounded-lg hover:bg-amber-600"
        >
          {submitting
            ? mode === "signin" ? "Signing in…" : "Activating…"
            : mode === "signin" ? "Sign in" : "Activate account"}
        </button>
      </form>
    </div>
  );
}
