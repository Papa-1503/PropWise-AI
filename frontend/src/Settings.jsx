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
 * setting (routers/organizations.py) - both shown only to staff, and
 * only functional for the org owner specifically, matching the real
 * ownership boundary the backend enforces. Notification preferences
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
