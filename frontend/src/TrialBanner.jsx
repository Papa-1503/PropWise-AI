import { useState, useEffect } from "react";
import { useAuth } from "./AuthContext";
import { useNavigate } from "react-router-dom";
import { AlertTriangle } from "lucide-react";
import { API_BASE } from "./config";

/**
 * TrialBanner
 *
 * Real, globally-visible surface for the trial/billing status the
 * backend now actually enforces (auth.py's _enforce_trial_status) -
 * without this, a staff member would only discover their trial had
 * expired the moment a real request came back 402, with no earlier
 * warning anywhere in the UI. Staff-only (tenants are never subject
 * to this), and silently renders nothing for an "internal" plan org
 * or a paid, healthy subscription - this is meant to be seen only
 * when there's something genuinely worth seeing.
 */
export default function TrialBanner() {
  const { user, authFetch } = useAuth();
  const [status, setStatus] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (user?.role !== "staff") return;
    authFetch(`${API_BASE}/billing/status`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => data && setStatus(data))
      .catch(() => {});
  }, [user?.role, authFetch]);

  if (!status || status.plan === "internal" || (status.plan === "pro" && status.active)) {
    return null;
  }

  const showWarning = status.blocked || (status.trialDaysLeft != null && status.trialDaysLeft <= 3);
  if (!showWarning) return null;

  return (
    <div
      className={`flex items-center justify-center gap-2 px-4 py-1.5 text-xs font-medium ${
        status.blocked ? "bg-rose-600 text-white" : "bg-amber-100 text-amber-800"
      }`}
    >
      <AlertTriangle size={13} />
      {status.blocked ? (
        <>Your free trial has ended.</>
      ) : (
        <>{status.trialDaysLeft} day{status.trialDaysLeft === 1 ? "" : "s"} left in your free trial.</>
      )}
      <button onClick={() => navigate("/app/settings")} className="underline font-semibold ml-1">
        {status.blocked ? "Subscribe now" : "Manage billing"}
      </button>
    </div>
  );
}
