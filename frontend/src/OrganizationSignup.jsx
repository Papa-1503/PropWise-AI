import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "./AuthContext";

/**
 * OrganizationSignup — the public /signup page.
 *
 * The real "create a brand-new company account" entry point, which
 * genuinely did not exist in the UI before this (only the backend
 * endpoint did). Distinct from LoginScreen's existing "signup" tab,
 * which is for a RESIDENT joining an already-existing organization's
 * property via invite code - this is for a property management
 * company creating its own new, independent account for the first
 * time.
 */
export default function OrganizationSignup() {
  const [organizationName, setOrganizationName] = useState("");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const { signupOrganization } = useAuth();
  const navigate = useNavigate();

  async function handleSubmit(e) {
    e.preventDefault();
    if (!organizationName.trim() || !name.trim() || !email.trim() || password.length < 8) {
      setError("Please fill in every field. Password must be at least 8 characters.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await signupOrganization({ organizationName: organizationName.trim(), name: name.trim(), email: email.trim(), password });
      navigate("/app/dashboard");
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 p-4">
      <div className="bg-white border border-slate-200 rounded-xl p-6 w-full max-w-sm">
        <div className="flex items-center gap-2 mb-1">
          <div className="w-8 h-8 bg-gradient-to-br from-indigo-600 to-fuchsia-600 rounded-lg flex items-center justify-center shrink-0">
            <span className="text-white font-bold text-sm">R</span>
          </div>
          <span className="font-serif font-bold text-slate-900">PropWise AI</span>
        </div>
        <h1 className="text-lg font-semibold mt-3 mb-1">Create your organization</h1>
        <p className="text-xs text-slate-500 mb-4">
          Start your 14-day trial. No credit card required yet.
        </p>

        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label htmlFor="orgName" className="text-xs text-slate-500">Company name</label>
            <input
              id="orgName"
              value={organizationName}
              onChange={(e) => setOrganizationName(e.target.value)}
              placeholder="Sunset Property Management"
              className="w-full text-sm border border-slate-200 rounded px-2 py-1.5 mt-0.5"
            />
          </div>
          <div>
            <label htmlFor="yourName" className="text-xs text-slate-500">Your name</label>
            <input
              id="yourName"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full text-sm border border-slate-200 rounded px-2 py-1.5 mt-0.5"
            />
          </div>
          <div>
            <label htmlFor="email" className="text-xs text-slate-500">Email</label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full text-sm border border-slate-200 rounded px-2 py-1.5 mt-0.5"
            />
          </div>
          <div>
            <label htmlFor="password" className="text-xs text-slate-500">Password (min. 8 characters)</label>
            <input
              id="password"
              type="password"
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full text-sm border border-slate-200 rounded px-2 py-1.5 mt-0.5"
            />
          </div>

          {error && <p role="alert" className="text-xs text-rose-600 bg-rose-50 border border-rose-200 rounded px-3 py-2">{error}</p>}

          <button
            type="submit"
            disabled={saving}
            className="w-full bg-slate-900 disabled:bg-slate-300 text-white text-sm font-semibold py-2.5 rounded-lg hover:bg-slate-800"
          >
            {saving ? "Creating…" : "Start free trial"}
          </button>
        </form>

        <p className="text-[11px] text-slate-400 mt-4 text-center">
          Already have an account? <a href="/" className="text-indigo-600 underline">Sign in</a>
        </p>
      </div>
    </div>
  );
}
