import { useState } from "react";
import { useAuth } from "./AuthContext";
import { useToast } from "./ToastContext";
import { API_BASE } from "./config";

/**
 * Settings
 *
 * Modeled on the shared design's tabbed Settings page, but honestly
 * scoped down: that design had Profile/Notifications/Billing/Security
 * tabs, but PropWise AI has no real backend behind notification
 * preferences at the user level, and no real subscription/billing
 * system for itself as a product. Building those tabs would mean UI
 * with nothing functional behind it — the same category of gap flagged
 * and avoided in the original PropWise AI assessment. Built the two tabs
 * that have genuine, real capability: editing your name, and changing
 * your password (neither existed anywhere in the app before this).
 */

function ProfileTab() {
  const { user, setUser, authFetch } = useAuth();
  const [name, setName] = useState(user?.name || "");
  const [saving, setSaving] = useState(false);
  const { show: showToast } = useToast();

  async function handleSave() {
    if (!name.trim()) {
      showToast("Name can't be empty.", "error");
      return;
    }
    setSaving(true);
    try {
      const res = await authFetch(`${API_BASE}/auth/me`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name.trim() }),
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

export default function Settings() {
  const [tab, setTab] = useState("profile");

  return (
    <div className="max-w-lg mx-auto">
      <h2 className="text-lg font-semibold mb-3">Settings</h2>
      <div className="flex gap-1 bg-slate-100 rounded-full p-0.5 w-fit mb-4">
        {[["profile", "Profile"], ["security", "Security"]].map(([id, label]) => (
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
      {tab === "profile" ? <ProfileTab /> : <SecurityTab />}
    </div>
  );
}
