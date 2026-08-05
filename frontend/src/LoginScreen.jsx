import { useState } from "react";
import { useAuth } from "./AuthContext";

/**
 * LoginScreen
 *
 * Real staff/resident login — calls POST /api/auth/login and stores a
 * real JWT via AuthContext. Role is determined by the account itself
 * (returned from the backend), not chosen client-side.
 *
 * Sign-up is for tenants: the backend always forces role="tenant" on
 * /register regardless of what's submitted here, and propertyId/unitId
 * only take effect if a matching lease record (created by staff) already
 * exists for that email — otherwise the account is created with no unit
 * access until staff sets that up. New staff accounts are provisioned by
 * an existing staff member, not through this public form.
 */
export default function LoginScreen() {
  const { login, register } = useAuth();
  const [mode, setMode] = useState("signin"); // "signin" | "signup"
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [propertyId, setPropertyId] = useState("");
  const [unitId, setUnitId] = useState("");
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
        await register({
          email,
          password,
          name,
          propertyId: propertyId || undefined,
          unitId: unitId || undefined,
        });
      }
    } catch (err) {
      setError(err.message || "Something went wrong.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#f6f3ec]">
      <form
        onSubmit={handleSubmit}
        className="bg-white border border-slate-200 rounded-xl p-9 w-[340px] text-center shadow-sm"
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
            Sign Up
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
              placeholder="Property ID (optional)"
              value={propertyId}
              onChange={(e) => setPropertyId(e.target.value)}
              className="w-full text-sm border border-slate-200 rounded-md px-3 py-2 mb-2"
            />
            <input
              type="text"
              placeholder="Unit ID (optional)"
              value={unitId}
              onChange={(e) => setUnitId(e.target.value)}
              className="w-full text-sm border border-slate-200 rounded-md px-3 py-2 mb-2"
            />
            <p className="text-[10px] text-slate-400 mb-2 text-left">
              Property/Unit only link your account if they match a lease your property manager already created for this email.
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
            ? mode === "signin" ? "Signing in…" : "Creating account…"
            : mode === "signin" ? "Sign in" : "Create account"}
        </button>
      </form>
    </div>
  );
}
