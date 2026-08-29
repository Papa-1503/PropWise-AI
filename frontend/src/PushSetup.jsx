import { useState, useEffect } from "react";
import { useAuth } from "./AuthContext";
import { useToast } from "./ToastContext";
import { API_BASE } from "./config";
import { Bell, X } from "lucide-react";

/**
 * PushSetup — Priority 8, Step 1 (the permission-request half; the
 * service worker's push/notificationclick handling lives in src/sw.js).
 *
 * Gated on genuinely running in standalone/installed mode
 * (window.matchMedia('(display-mode: standalone)')), per the roadmap's
 * explicit guidance: "Request notification permission from the user
 * post-install (with a clear explanation of why, not a surprise
 * browser prompt)". Someone just browsing in a regular tab never sees
 * this — only people who've actually installed the app, and only
 * after a real explanation shown in our own UI, before the native
 * browser permission dialog ever appears.
 */

const DISMISS_KEY = "rentflow_push_setup_dismissed";

function base64UrlToUint8Array(base64Url) {
  const padding = "=".repeat((4 - (base64Url.length % 4)) % 4);
  const base64 = (base64Url + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(base64);
  return Uint8Array.from([...raw].map((c) => c.charCodeAt(0)));
}

export default function PushSetup() {
  const [dismissed, setDismissed] = useState(() => {
    try {
      return localStorage.getItem(DISMISS_KEY) === "true";
    } catch {
      return false;
    }
  });
  const [isStandalone, setIsStandalone] = useState(false);
  const [busy, setBusy] = useState(false);
  const { authFetch } = useAuth();
  const { show: showToast } = useToast();

  useEffect(() => {
    setIsStandalone(window.matchMedia("(display-mode: standalone)").matches);
  }, []);

  function dismiss() {
    setDismissed(true);
    try {
      localStorage.setItem(DISMISS_KEY, "true");
    } catch {
      // persistence is a nicety here, not required for this session
    }
  }

  async function enable() {
    if (!("Notification" in window) || !("serviceWorker" in navigator) || !("PushManager" in window)) {
      showToast("Push notifications aren't supported in this browser.", "error");
      dismiss();
      return;
    }
    setBusy(true);
    try {
      const permission = await Notification.requestPermission();
      if (permission !== "granted") {
        showToast("Notifications weren't enabled.", "info");
        dismiss();
        return;
      }

      const keyRes = await authFetch(`${API_BASE}/push/vapid-public-key`);
      if (!keyRes.ok) throw new Error("Push isn't configured on the server yet.");
      const { publicKey } = await keyRes.json();

      const registration = await navigator.serviceWorker.ready;
      const subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: base64UrlToUint8Array(publicKey),
      });

      const subJson = subscription.toJSON();
      const res = await authFetch(`${API_BASE}/push`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ endpoint: subJson.endpoint, keys: subJson.keys }),
      });
      if (!res.ok) throw new Error("Couldn't save your subscription.");

      showToast("Notifications enabled — you'll get alerts even when RentFlow AI is closed.", "success");
      dismiss();
    } catch (err) {
      showToast(err.message || "Couldn't enable notifications.", "error");
    } finally {
      setBusy(false);
    }
  }

  if (dismissed || !isStandalone) return null;

  return (
    <div className="fixed bottom-4 right-4 z-[114] bg-white border border-slate-200 rounded-2xl shadow-xl p-4 max-w-xs">
      <button onClick={dismiss} className="absolute top-2 right-2 text-slate-300 hover:text-slate-500" aria-label="Dismiss">
        <X size={15} />
      </button>
      <div className="flex items-start gap-2.5">
        <span className="shrink-0 w-9 h-9 rounded-full bg-indigo-100 flex items-center justify-center">
          <Bell size={16} className="text-indigo-600" />
        </span>
        <div>
          <p className="text-sm font-semibold text-slate-800">Stay in the loop</p>
          <p className="text-xs text-slate-500 mt-0.5">
            Get notified about urgent tickets, payments, and updates — even when RentFlow AI isn't open.
          </p>
        </div>
      </div>
      <button
        onClick={enable}
        disabled={busy}
        className="mt-3 w-full text-sm font-semibold bg-slate-900 disabled:bg-slate-300 text-white py-2 rounded-lg"
      >
        {busy ? "Enabling…" : "Enable notifications"}
      </button>
    </div>
  );
}
