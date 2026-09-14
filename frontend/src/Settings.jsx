import { useState, useEffect } from "react";
import { useAuth } from "./AuthContext";
import { useToast } from "./ToastContext";
import { API_BASE } from "./config";

/**
 * Settings
 *
 * Modeled on the shared design's tabbed Settings page. Profile and
 * Security are the two tabs with genuine, real capability that
 * existed before this pass (editing your name, changing your
 * password). Billing is real (routers/billing.py, billing_service.py),
 * now with real multi-tier pricing (Starter/Growth/Pro - see that
 * router's own module docstring for the market reasoning behind the
 * 3 tiers) rather than one flat plan - the trial view shows all 3 as
 * real, subscribable cards with an honest "recommended for you" badge
 * driven by the org's own live unit count, never a hard gate.
 * Organization now covers the real, optional dedicated-SMS-number
 * setting (routers/organizations.py), a real, self-serve export of
 * the organization's entire dataset (routers/data_export.py, see
 * ExportDataSection's own docstring), and a real, embeddable vacancy
 * listings widget (routers/public_listings.py, see
 * VacancyWidgetSection's own docstring) - all shown only to staff, and
 * only functional for the org owner specifically, matching the real
 * ownership boundary the backend enforces. Security now also covers
 * real two-factor authentication (routers/two_factor.py) - see
 * TwoFactorSection's own docstring below. Notification preferences
 * at the user level still have no real backend behind them -
 * deliberately not added as a tab to avoid UI with nothing functional
 * behind it.
 */

function ProfileTab() {
  const { user, setUser, authFetch } = useAuth();
  const [name, setName] = useState(user?.name || "");
  const [preferredLanguage, setPreferredLanguage] = useState(user?.preferredLanguage || "en");
  const [languages, setLanguages] = useState({ en: "English" });
  const [saving, setSaving] = useState(false);
  const { show: showToast } = useToast();

  useEffect(() => {
    if (user?.role !== "tenant") return;
    // Real, current supported-language set from the backend, not a
    // hardcoded copy that could silently drift out of sync with it.
    authFetch(`${API_BASE}/auth/languages`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => data && setLanguages(data.languages))
      .catch(() => {});
  }, [user?.role, authFetch]);

  async function handleSave() {
    if (!name.trim()) {
      showToast("Name can't be empty.", "error");
      return;
    }
    setSaving(true);
    try {
      const body = { name: name.trim() };
      if (user?.role === "tenant") body.preferredLanguage = preferredLanguage;
      const res = await authFetch(`${API_BASE}/auth/me`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Couldn't save.");
      setUser?.(data);
      showToast("Profile updated.", "success");
    } catch (err) {
      showToast(err.message, "error");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5 space-y-4">
      <h3 className="text-sm font-semibold">Profile</h3>
      <div>
        <label className="text-xs text-slate-500">Name</label>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="w-full text-sm border border-slate-200 rounded px-2 py-1.5 mt-0.5"
        />
      </div>
      <div>
        <label className="text-xs text-slate-500">Email</label>
        <input
          value={user?.email || ""}
          disabled
          title="Email is your login identifier and can't be changed here."
          className="w-full text-sm border border-slate-200 rounded px-2 py-1.5 mt-0.5 bg-slate-50 text-slate-400"
        />
      </div>
      {user?.role === "tenant" && (
        <div>
          <label className="text-xs text-slate-500">Preferred language</label>
          <select
            value={preferredLanguage}
            onChange={(e) => setPreferredLanguage(e.target.value)}
            className="w-full text-sm border border-slate-200 rounded px-2 py-1.5 mt-0.5"
          >
            {Object.entries(languages).map(([code, name]) => (
              <option key={code} value={code}>{name}</option>
            ))}
          </select>
          <p className="text-[11px] text-slate-400 mt-1">
            Notifications and the help assistant will be translated into this language.
          </p>
        </div>
      )}
      <button
        onClick={handleSave}
        disabled={saving}
        className="text-sm font-semibold bg-slate-900 disabled:bg-slate-300 text-white px-4 py-2 rounded-lg"
      >
        {saving ? "Saving…" : "Save changes"}
      </button>

      <div className="pt-3 border-t border-slate-100">
        <button
          onClick={() => {
            try {
              localStorage.removeItem("rentflow_onboarding_complete");
            } catch {
              // ignore — worst case the tour just doesn't reset, nothing breaks
            }
            window.location.reload();
          }}
          className="text-xs text-indigo-700 hover:underline"
        >
          Replay the onboarding tour
        </button>
      </div>
    </div>
  );
}

function SecurityTab() {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [saving, setSaving] = useState(false);
  const { authFetch } = useAuth();
  const { show: showToast } = useToast();

  async function handleSave() {
    if (newPassword.length < 8) {
      showToast("New password must be at least 8 characters.", "error");
      return;
    }
    if (newPassword !== confirmPassword) {
      showToast("New password and confirmation don't match.", "error");
      return;
    }
    setSaving(true);
    try {
      const res = await authFetch(`${API_BASE}/auth/change-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ currentPassword, newPassword }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Couldn't change password.");
      showToast("Password changed.", "success");
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (err) {
      showToast(err.message, "error");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-4">
    <div className="bg-white border border-slate-200 rounded-xl p-5 space-y-4">
      <h3 className="text-sm font-semibold">Change password</h3>
      <div>
        <label className="text-xs text-slate-500">Current password</label>
        <input
          type="password"
          autoComplete="current-password"
          value={currentPassword}
          onChange={(e) => setCurrentPassword(e.target.value)}
          className="w-full text-sm border border-slate-200 rounded px-2 py-1.5 mt-0.5"
        />
      </div>
      <div>
        <label className="text-xs text-slate-500">New password (min. 8 characters)</label>
        <input
          type="password"
          autoComplete="new-password"
          value={newPassword}
          onChange={(e) => setNewPassword(e.target.value)}
          className="w-full text-sm border border-slate-200 rounded px-2 py-1.5 mt-0.5"
        />
      </div>
      <div>
        <label className="text-xs text-slate-500">Confirm new password</label>
        <input
          type="password"
          autoComplete="new-password"
          value={confirmPassword}
          onChange={(e) => setConfirmPassword(e.target.value)}
          className="w-full text-sm border border-slate-200 rounded px-2 py-1.5 mt-0.5"
        />
      </div>
      <button
        onClick={handleSave}
        disabled={saving}
        className="text-sm font-semibold bg-slate-900 disabled:bg-slate-300 text-white px-4 py-2 rounded-lg"
      >
        {saving ? "Saving…" : "Update password"}
      </button>
    </div>
    <TwoFactorSection />
    </div>
  );
}

/**
 * TwoFactorSection
 *
 * Real setup flow for backend routers/two_factor.py - a genuine,
 * multi-step wizard (setup -> scan/confirm -> backup codes shown
 * once), not a single toggle, since a toggle would hide the real
 * step where the user's authenticator app is actually confirmed
 * working before 2FA is enabled (see that router's own module
 * docstring for why that confirm step is mandatory, not optional).
 */
function TwoFactorSection() {
  const { authFetch } = useAuth();
  const { show: showToast } = useToast();
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [wizardStep, setWizardStep] = useState(null); // null | "scan" | "backupCodes"
  const [setupData, setSetupData] = useState(null);
  const [confirmCode, setConfirmCode] = useState("");
  const [backupCodes, setBackupCodes] = useState(null);
  const [disablePassword, setDisablePassword] = useState("");
  const [showDisableForm, setShowDisableForm] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    authFetch(`${API_BASE}/auth/2fa/status`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => data && setStatus(data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [authFetch]);

  async function handleStartSetup() {
    setBusy(true);
    try {
      const res = await authFetch(`${API_BASE}/auth/2fa/setup`, { method: "POST" });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Couldn't start setup.");
      setSetupData(data);
      setWizardStep("scan");
    } catch (err) {
      showToast(err.message, "error");
    } finally {
      setBusy(false);
    }
  }

  async function handleConfirmCode() {
    setBusy(true);
    try {
      const res = await authFetch(`${API_BASE}/auth/2fa/enable`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code: confirmCode.trim() }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "That code didn't match.");
      setBackupCodes(data.backupCodes);
      setWizardStep("backupCodes");
      setStatus({ enabled: true });
    } catch (err) {
      showToast(err.message, "error");
    } finally {
      setBusy(false);
    }
  }

  function handleFinishWizard() {
    setWizardStep(null);
    setSetupData(null);
    setConfirmCode("");
    setBackupCodes(null);
  }

  async function handleDisable() {
    setBusy(true);
    try {
      const res = await authFetch(`${API_BASE}/auth/2fa/disable`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password: disablePassword }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Couldn't disable two-factor authentication.");
      setStatus({ enabled: false });
      setShowDisableForm(false);
      setDisablePassword("");
      showToast("Two-factor authentication turned off.", "success");
    } catch (err) {
      showToast(err.message, "error");
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return <div className="bg-white border border-slate-200 rounded-xl p-5 text-sm text-slate-400">Loading…</div>;
  }

  if (wizardStep === "scan") {
    return (
      <div className="bg-white border border-slate-200 rounded-xl p-5 space-y-3">
        <h3 className="text-sm font-semibold">Set up two-factor authentication</h3>
        <p className="text-xs text-slate-500">
          Scan this QR code with an authenticator app (Google Authenticator, Authy, 1Password, etc.), then enter the 6-digit code it shows.
        </p>
        <img src={setupData.qrCodeDataUri} alt="Two-factor setup QR code" className="w-40 h-40 mx-auto border border-slate-200 rounded-lg" />
        <p className="text-[11px] text-slate-400 text-center">
          Can't scan? Enter this code manually: <span className="font-mono">{setupData.secret}</span>
        </p>
        <div>
          <label className="text-xs text-slate-500">6-digit code</label>
          <input
            value={confirmCode}
            onChange={(e) => setConfirmCode(e.target.value)}
            placeholder="123456"
            className="w-full text-sm text-center tracking-widest font-mono border border-slate-200 rounded px-2 py-1.5 mt-0.5"
          />
        </div>
        <div className="flex gap-2">
          <button
            onClick={handleConfirmCode}
            disabled={busy || confirmCode.trim().length < 6}
            className="text-sm font-semibold bg-indigo-600 disabled:bg-indigo-300 text-white px-4 py-2 rounded-lg"
          >
            {busy ? "Verifying…" : "Confirm & enable"}
          </button>
          <button onClick={handleFinishWizard} className="text-sm text-slate-500 px-4 py-2">Cancel</button>
        </div>
      </div>
    );
  }

  if (wizardStep === "backupCodes") {
    return (
      <div className="bg-white border border-slate-200 rounded-xl p-5 space-y-3">
        <h3 className="text-sm font-semibold text-emerald-700">Two-factor authentication is on</h3>
        <p className="text-xs text-slate-600">
          Save these backup codes somewhere safe — each one can be used once if you lose access to your authenticator app.
          They won't be shown again.
        </p>
        <div className="grid grid-cols-2 gap-1.5 bg-slate-50 border border-slate-200 rounded-lg p-3 font-mono text-sm">
          {backupCodes.map((code) => (
            <span key={code}>{code}</span>
          ))}
        </div>
        <button
          onClick={handleFinishWizard}
          className="text-sm font-semibold bg-slate-900 text-white px-4 py-2 rounded-lg"
        >
          I've saved these — done
        </button>
      </div>
    );
  }

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5 space-y-3">
      <h3 className="text-sm font-semibold">Two-factor authentication</h3>
      {status?.enabled ? (
        <>
          <p className="text-sm text-emerald-700 font-medium">Enabled — your account requires a code at sign-in.</p>
          {!showDisableForm ? (
            <button
              onClick={() => setShowDisableForm(true)}
              className="text-xs font-semibold text-rose-600 border border-rose-200 px-3 py-1.5 rounded-lg"
            >
              Turn off
            </button>
          ) : (
            <div className="space-y-2">
              <label className="text-xs text-slate-500">Confirm your password to turn it off</label>
              <input
                type="password"
                value={disablePassword}
                onChange={(e) => setDisablePassword(e.target.value)}
                className="w-full text-sm border border-slate-200 rounded px-2 py-1.5"
              />
              <div className="flex gap-2">
                <button
                  onClick={handleDisable}
                  disabled={busy}
                  className="text-xs font-semibold bg-rose-600 disabled:bg-rose-300 text-white px-3 py-1.5 rounded-lg"
                >
                  {busy ? "Turning off…" : "Confirm turn off"}
                </button>
                <button onClick={() => { setShowDisableForm(false); setDisablePassword(""); }} className="text-xs text-slate-500">Cancel</button>
              </div>
            </div>
          )}
        </>
      ) : (
        <>
          <p className="text-xs text-slate-500">
            Add a real second step at sign-in using an authenticator app — recommended, especially for the organization owner.
          </p>
          <button
            onClick={handleStartSetup}
            disabled={busy}
            className="text-sm font-semibold bg-slate-900 disabled:bg-slate-300 text-white px-4 py-2 rounded-lg"
          >
            {busy ? "Starting…" : "Set up two-factor authentication"}
          </button>
        </>
      )}
    </div>
  );
}

function BillingTab() {
  const { user, authFetch } = useAuth();
  const [status, setStatus] = useState(null);
  const [tiersData, setTiersData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(null);
  const { show: showToast } = useToast();

  useEffect(() => {
    Promise.all([
      authFetch(`${API_BASE}/billing/status`).then((res) => (res.ok ? res.json() : null)),
      authFetch(`${API_BASE}/billing/tiers`).then((res) => (res.ok ? res.json() : null)),
    ])
      .then(([statusData, tiers]) => {
        if (statusData) setStatus(statusData);
        if (tiers) setTiersData(tiers);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [authFetch]);

  async function handleUpgrade(tier) {
    setActionLoading(tier);
    try {
      const res = await authFetch(`${API_BASE}/billing/checkout`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tier,
          successUrl: `${window.location.origin}/app/settings?billingSuccess=true`,
          cancelUrl: `${window.location.origin}/app/settings`,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Couldn't start checkout.");
      window.location.href = data.checkoutUrl;
    } catch (err) {
      showToast(err.message, "error");
      setActionLoading(null);
    }
  }

  async function handleManage() {
    setActionLoading("manage");
    try {
      const res = await authFetch(`${API_BASE}/billing/portal`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ returnUrl: `${window.location.origin}/app/settings` }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Couldn't open billing management.");
      window.location.href = data.portalUrl;
    } catch (err) {
      showToast(err.message, "error");
      setActionLoading(null);
    }
  }

  if (!user?.isOrgOwner) {
    return (
      <div className="bg-white border border-slate-200 rounded-xl p-5">
        <h3 className="text-sm font-semibold mb-1">Billing</h3>
        <p className="text-sm text-slate-500">
          Only your organization's owner can view and manage billing.
        </p>
      </div>
    );
  }

  if (loading) {
    return <div className="bg-white border border-slate-200 rounded-xl p-5 text-sm text-slate-400">Loading…</div>;
  }

  if (!status) {
    return (
      <div className="bg-white border border-slate-200 rounded-xl p-5">
        <h3 className="text-sm font-semibold mb-1">Billing</h3>
        <p className="text-sm text-rose-600">Couldn't load billing status.</p>
      </div>
    );
  }

  const isPaid = status.plan === "pro" && status.active;
  const isInternal = status.plan === "internal";

  if (isInternal) {
    return (
      <div className="bg-white border border-slate-200 rounded-xl p-5 space-y-4">
        <h3 className="text-sm font-semibold">Billing</h3>
        <p className="text-sm text-slate-600">This organization isn't subject to billing.</p>
      </div>
    );
  }

  if (isPaid) {
    const currentTierInfo = tiersData?.tiers?.find((t) => t.id === status.billingTier);
    return (
      <div className="bg-white border border-slate-200 rounded-xl p-5 space-y-3">
        <h3 className="text-sm font-semibold">Billing</h3>
        <p className="text-sm text-emerald-700 font-medium">
          You're on the {currentTierInfo?.name || status.billingTier || "paid"} plan
          {currentTierInfo ? ` — $${currentTierInfo.price}/month` : ""}.
        </p>
        {status.subscriptionStatus && status.subscriptionStatus !== "active" && (
          <p className="text-xs text-amber-600">
            Subscription status: {status.subscriptionStatus} — check your payment method if this persists.
          </p>
        )}
        <p className="text-xs text-slate-500">
          To change tiers or update your payment method, use the billing portal — it lets you switch
          between Starter, Growth, and Pro directly.
        </p>
        <button
          onClick={handleManage}
          disabled={actionLoading === "manage"}
          className="text-sm font-semibold bg-slate-900 disabled:bg-slate-300 text-white px-4 py-2 rounded-lg"
        >
          {actionLoading === "manage" ? "Opening…" : "Manage billing"}
        </button>
      </div>
    );
  }

  // Trial (active or expired) - show real tier cards to choose from
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5 space-y-4">
      <h3 className="text-sm font-semibold">Billing</h3>
      {status.blocked ? (
        <p className="text-sm text-rose-600 font-medium">
          Your free trial has ended. Choose a plan below to keep using PropWise AI.
        </p>
      ) : (
        <p className="text-sm text-slate-600">
          {status.trialDaysLeft != null
            ? `${status.trialDaysLeft} day${status.trialDaysLeft === 1 ? "" : "s"} left in your free trial.`
            : "You're on a free trial."}{" "}
          Choose a plan whenever you're ready.
        </p>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {(tiersData?.tiers || []).map((tier) => {
          const isRecommended = tiersData?.recommendedTier === tier.id;
          return (
            <div
              key={tier.id}
              className={`rounded-xl border p-4 flex flex-col ${
                isRecommended ? "border-indigo-400 ring-1 ring-indigo-200 bg-indigo-50/40" : "border-slate-200"
              }`}
            >
              {isRecommended && (
                <span className="text-[10px] font-bold uppercase tracking-wide text-indigo-700 mb-1.5">
                  Recommended for you
                </span>
              )}
              <p className="text-sm font-semibold">{tier.name}</p>
              <p className="text-xl font-bold mt-1">${tier.price}<span className="text-xs font-normal text-slate-500">/mo</span></p>
              <p className="text-xs text-slate-500 mt-1 mb-3">{tier.unitGuidance}</p>
              <button
                onClick={() => handleUpgrade(tier.id)}
                disabled={actionLoading === tier.id}
                className={`mt-auto text-xs font-semibold px-3 py-2 rounded-lg ${
                  isRecommended
                    ? "bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-300 text-white"
                    : "bg-slate-900 hover:bg-slate-800 disabled:bg-slate-300 text-white"
                }`}
              >
                {actionLoading === tier.id ? "Redirecting…" : "Subscribe"}
              </button>
            </div>
          );
        })}
      </div>
      {tiersData && (
        <p className="text-[11px] text-slate-400">
          You currently have {tiersData.yourUnitCount} unit{tiersData.yourUnitCount === 1 ? "" : "s"} across your properties.
        </p>
      )}
    </div>
  );
}

function OrganizationTab() {
  const { user, authFetch } = useAuth();
  const [smsNumber, setSmsNumber] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const { show: showToast } = useToast();

  useEffect(() => {
    authFetch(`${API_BASE}/organizations/me`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => data && setSmsNumber(data.smsNumber || ""))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [authFetch]);

  async function handleSave() {
    setSaving(true);
    try {
      const res = await authFetch(`${API_BASE}/organizations/me`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ smsNumber: smsNumber.trim() || null }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Couldn't save.");
      showToast("Saved.", "success");
    } catch (err) {
      showToast(err.message, "error");
    } finally {
      setSaving(false);
    }
  }

  if (!user?.isOrgOwner) {
    return (
      <div className="bg-white border border-slate-200 rounded-xl p-5">
        <h3 className="text-sm font-semibold mb-1">Organization</h3>
        <p className="text-sm text-slate-500">
          Only your organization's owner can view and manage these settings.
        </p>
      </div>
    );
  }

  if (loading) {
    return <div className="bg-white border border-slate-200 rounded-xl p-5 text-sm text-slate-400">Loading…</div>;
  }

  return (
    <div className="space-y-4">
    <div className="bg-white border border-slate-200 rounded-xl p-5 space-y-3">
      <h3 className="text-sm font-semibold">Dedicated SMS number</h3>
      <p className="text-xs text-slate-500">
        By default, your organization shares one text number with every other
        organization on PropWise AI — texts your residents receive, and texts
        they send back, aren't guaranteed to be uniquely matched to your
        organization. Configuring your own dedicated Twilio number here fixes
        that: your residents' texts will always be correctly matched to your
        organization, and outgoing texts will come from a number specific to
        you. Requires purchasing a number in your own Twilio account and
        pointing its Messaging webhook at this app's SMS endpoint.
      </p>
      <div>
        <label className="text-xs text-slate-500">Phone number (E.164 format)</label>
        <input
          value={smsNumber}
          onChange={(e) => setSmsNumber(e.target.value)}
          placeholder="+15551234567"
          className="w-full text-sm border border-slate-200 rounded px-2 py-1.5 mt-0.5 font-mono"
        />
      </div>
      <button
        onClick={handleSave}
        disabled={saving}
        className="text-sm font-semibold bg-slate-900 disabled:bg-slate-300 text-white px-4 py-2 rounded-lg"
      >
        {saving ? "Saving…" : "Save changes"}
      </button>
    </div>
    <VacancyWidgetSection />
    <ExportDataSection />
    </div>
  );
}

/**
 * VacancyWidgetSection
 *
 * Real, copy-paste embed code for backend routers/public_listings.py's
 * vacancy-widget.js - a genuine competitive angle: a free, always-
 * current listing widget staff can drop directly onto their OWN
 * company website, outside PropWise AI entirely. orgId is pre-filled
 * from the real, logged-in user's own account - never something staff
 * have to go find or copy from elsewhere.
 */
function VacancyWidgetSection() {
  const { user } = useAuth();
  const { show: showToast } = useToast();
  const embedCode = `<div id="propwise-vacancies"></div>\n<script src="${API_BASE}/public/vacancy-widget.js" data-org-id="${user?.orgId || ""}" defer></script>`;

  function handleCopy() {
    navigator.clipboard.writeText(embedCode)
      .then(() => showToast("Embed code copied.", "success"))
      .catch(() => showToast("Couldn't copy — select and copy manually.", "error"));
  }

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5 space-y-3">
      <h3 className="text-sm font-semibold">Vacancy listings widget</h3>
      <p className="text-xs text-slate-500">
        Show your currently available units directly on your own website — always up to date, no manual
        updates needed. Paste this snippet anywhere in your site's HTML.
      </p>
      <pre className="text-[11px] bg-slate-900 text-slate-100 rounded-lg p-3 overflow-x-auto whitespace-pre-wrap break-all">
        {embedCode}
      </pre>
      <button
        onClick={handleCopy}
        className="text-sm font-semibold bg-slate-900 text-white px-4 py-2 rounded-lg"
      >
        Copy embed code
      </button>
    </div>
  );
}

/**
 * ExportDataSection
 *
 * Real, self-serve export of everything this organization owns (backend:
 * routers/data_export.py) - genuinely missing before this. Downloads a
 * single JSON file directly via the browser's normal file-download
 * mechanism (an <a> click on an object URL), not a new tab or a raw
 * fetch response left dangling - the same real pattern already
 * established for downloading the CSV import templates in
 * BulkImport.jsx.
 */
function ExportDataSection() {
  const { authFetch } = useAuth();
  const { show: showToast } = useToast();
  const [exporting, setExporting] = useState(false);

  async function handleExport() {
    setExporting(true);
    try {
      const res = await authFetch(`${API_BASE}/organizations/me/export`);
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || "Couldn't export your data.");
      }
      const blob = await res.blob();
      const contentDisposition = res.headers.get("Content-Disposition") || "";
      const match = contentDisposition.match(/filename="([^"]+)"/);
      const filename = match ? match[1] : "propwise_export.json";

      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      showToast(err.message, "error");
    } finally {
      setExporting(false);
    }
  }

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5 space-y-3">
      <h3 className="text-sm font-semibold">Export your data</h3>
      <p className="text-xs text-slate-500">
        Download everything your organization has stored in PropWise AI — properties, leases,
        maintenance history, payments, documents, and more — as a single file. Useful for your
        own records, or if you ever want to move to another system.
      </p>
      <button
        onClick={handleExport}
        disabled={exporting}
        className="text-sm font-semibold bg-slate-900 disabled:bg-slate-300 text-white px-4 py-2 rounded-lg"
      >
        {exporting ? "Preparing your export…" : "Download my data"}
      </button>
    </div>
  );
}

export default function Settings() {
  const { user } = useAuth();
  const [tab, setTab] = useState("profile");

  const tabs = [["profile", "Profile"], ["security", "Security"]];
  if (user?.role === "staff") tabs.push(["billing", "Billing"], ["organization", "Organization"]);

  return (
    <div className="max-w-lg mx-auto">
      <h2 className="text-lg font-semibold mb-3">Settings</h2>
      <div className="flex gap-1 bg-slate-100 rounded-full p-0.5 w-fit mb-4">
        {tabs.map(([id, label]) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={`text-xs font-semibold px-3 py-1.5 rounded-full ${
              tab === id ? "bg-white shadow-sm text-slate-800" : "text-slate-500"
            }`}
          >
            {label}
          </button>
        ))}
      </div>
      {tab === "profile" ? <ProfileTab /> : tab === "security" ? <SecurityTab /> : tab === "billing" ? <BillingTab /> : <OrganizationTab />}
    </div>
  );
}
