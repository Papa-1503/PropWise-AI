import { useState } from "react";
import { useAuth } from "./AuthContext";

/**
 * LoginScreen
 *
 * Real staff/resident login — calls POST /api/auth/login and stores a
 * real JWT via AuthContext. Role is determined by the account itself
 * (returned from the backend), not chosen client-side like the old mockup.
 */
export default function LoginScreen() {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await login(email, password);
      // AuthContext's user state updates; parent app should route based on user.role
    } catch (err) {
      setError(err.message || "Something went wrong signing in.");
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
          {submitting ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}
