import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { API_BASE } from "./config";

/**
 * ResetPassword — the public /reset-password/:token page a user lands
 * on from the real email link forgot-password sends (see
 * routers/auth.py's /forgot-password and /reset-password).
 *
 * Deliberately its own standalone page, not folded into LoginScreen's
 * tab pattern - the token is real, single-use, and time-limited, so
 * this needs its own URL a person can open directly from an email
 * client, not a UI state reachable only by clicking through the app.
 */
export default function ResetPassword() {
  const { token } = useParams();
  const navigate = useNavigate();
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [done, setDone] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    if (newPassword.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    if (newPassword !== confirmPassword) {
      setError("Passwords don't match.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/auth/reset-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, newPassword }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Couldn't reset your password.");
      setDone(true);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  if (done) {
    return (
      <div className="min-h-screen flex items-center justify-center login-skyline-bg px-4">
        <div className="bg-white border border-slate-200 rounded-xl p-9 w-full max-w-[340px] text-center shadow-lg">
          <h1 className="text-lg font-semibold mb-2">Password updated</h1>
          <p className="text-sm text-slate-500 mb-4">You can now sign in with your new password.</p>
          <button
            onClick={() => navigate("/")}
            className="w-full bg-amber-700 text-white text-sm font-semibold py-2.5 rounded-lg hover:bg-amber-800"
          >
            Go to sign in
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center login-skyline-bg px-4">
      <form
        onSubmit={handleSubmit}
        className="bg-white border border-slate-200 rounded-xl p-9 w-full max-w-[340px] text-center shadow-lg"
      >
        <h1 className="text-lg font-semibold mb-1">Set a new password</h1>
        <p className="text-xs text-slate-500 mb-4">
          This link is single-use and expires an hour after it was sent.
        </p>

        <div className="text-left mb-2">
          <label htmlFor="newPassword" className="sr-only">New password</label>
          <input
            id="newPassword"
            type="password"
            required
            autoComplete="new-password"
            placeholder="New password (min. 8 characters)"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            className="w-full text-sm border border-slate-200 rounded-md px-3 py-2"
          />
        </div>
        <div className="text-left mb-2">
          <label htmlFor="confirmPassword" className="sr-only">Confirm new password</label>
          <input
            id="confirmPassword"
            type="password"
            required
            autoComplete="new-password"
            placeholder="Confirm new password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            className="w-full text-sm border border-slate-200 rounded-md px-3 py-2"
          />
        </div>

        {error && (
          <p role="alert" aria-live="polite" className="text-xs text-rose-600 bg-rose-50 border border-rose-200 rounded px-3 py-2 mt-2 text-left">
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={submitting}
          className="w-full mt-3 bg-amber-700 disabled:bg-slate-300 text-white text-sm font-semibold py-2.5 rounded-lg hover:bg-amber-800"
        >
          {submitting ? "Saving…" : "Set new password"}
        </button>
      </form>
    </div>
  );
}
