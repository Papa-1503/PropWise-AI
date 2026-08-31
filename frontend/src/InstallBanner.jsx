import { useState, useEffect } from "react";
import { Download, X } from "lucide-react";

/**
 * PWA install-prompt banner — the last item from the original
 * PropWise AI-inspired design-gap catalog.
 *
 * IMPORTANT PLATFORM LIMITATION, not a bug: `beforeinstallprompt` is a
 * Chrome/Edge/Android-only browser API. Safari on iOS has no equivalent
 * event and no programmatic install trigger at all — installing there
 * is a manual Share-sheet action with no way for a website to detect
 * installability or show a custom prompt. This banner will correctly
 * never appear on iOS Safari; that's expected, not something to debug.
 */

const DISMISS_KEY = "rentflow_pwa_banner_dismissed";

export default function InstallBanner() {
  const [deferredPrompt, setDeferredPrompt] = useState(null);
  const [dismissed, setDismissed] = useState(() => {
    try {
      return localStorage.getItem(DISMISS_KEY) === "true";
    } catch {
      return false;
    }
  });

  useEffect(() => {
    function handler(e) {
      e.preventDefault();
      setDeferredPrompt(e);
    }
    window.addEventListener("beforeinstallprompt", handler);
    return () => window.removeEventListener("beforeinstallprompt", handler);
  }, []);

  function dismiss() {
    setDismissed(true);
    try {
      localStorage.setItem(DISMISS_KEY, "true");
    } catch {
      // persistence is a nicety here, not required for this session
    }
  }

  async function install() {
    if (!deferredPrompt) return;
    deferredPrompt.prompt();
    await deferredPrompt.userChoice;
    // Whatever the user chose, the browser won't fire beforeinstallprompt
    // again for this same deferred event — clear it either way.
    setDeferredPrompt(null);
  }

  if (dismissed || !deferredPrompt) return null;

  return (
    <div className="fixed bottom-4 left-1/2 -translate-x-1/2 z-[115] bg-white border border-slate-200 rounded-2xl shadow-xl px-4 py-3 flex items-center gap-3 max-w-sm w-[calc(100%-2rem)]">
      <div className="w-10 h-10 bg-gradient-to-br from-indigo-600 to-fuchsia-600 rounded-lg flex items-center justify-center shrink-0">
        <span className="text-white font-bold text-sm">R</span>
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold text-slate-800">Install PropWise AI</p>
        <p className="text-xs text-slate-500">Quick access from your home screen</p>
      </div>
      <button
        onClick={install}
        className="shrink-0 flex items-center gap-1 text-xs font-semibold bg-slate-900 text-white px-3 py-2 rounded-lg"
      >
        <Download size={13} />
        Install
      </button>
      <button onClick={dismiss} className="shrink-0 text-slate-300 hover:text-slate-500" aria-label="Dismiss">
        <X size={16} />
      </button>
    </div>
  );
}
