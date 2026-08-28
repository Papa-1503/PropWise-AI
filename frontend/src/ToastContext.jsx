import { createContext, useContext, useState, useCallback, useRef } from "react";
import { CheckCircle2, XCircle, AlertTriangle, Info } from "lucide-react";

/**
 * A real, reusable toast system — genuinely global via context, not
 * another one-off like the undo toast built earlier today inside
 * MaintenanceTickets.jsx (which stays as-is; it's a specific
 * confirm/undo pattern, not a generic notification). Any component can
 * call useToast().show(message, type) from anywhere in the app.
 *
 * Supports real stacking: multiple toasts firing close together (e.g.
 * a bulk action's several results) show as a stacked list, each with
 * its own independent auto-dismiss timer, rather than only ever
 * showing one at a time.
 */

const ToastContext = createContext(null);

const TYPE_CONFIG = {
  success: { icon: CheckCircle2, iconBg: "bg-emerald-100", iconColor: "text-emerald-600" },
  error: { icon: XCircle, iconBg: "bg-rose-100", iconColor: "text-rose-600" },
  warning: { icon: AlertTriangle, iconBg: "bg-amber-100", iconColor: "text-amber-600" },
  info: { icon: Info, iconBg: "bg-indigo-100", iconColor: "text-indigo-600" },
};

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const nextId = useRef(0);

  const dismiss = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const show = useCallback((message, type = "success", durationMs = 3500) => {
    const id = nextId.current++;
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => dismiss(id), durationMs);
    return id;
  }, [dismiss]);

  return (
    <ToastContext.Provider value={{ show, dismiss }}>
      {children}
      <div className="fixed top-4 right-4 z-[100] space-y-2 w-full max-w-xs">
        {toasts.map((t) => {
          const cfg = TYPE_CONFIG[t.type] || TYPE_CONFIG.info;
          const Icon = cfg.icon;
          return (
            <div
              key={t.id}
              role="alert"
              className="bg-white border border-slate-200 rounded-xl shadow-lg p-3 flex items-start gap-2.5 animate-toast-in"
            >
              <span className={`shrink-0 w-7 h-7 rounded-full flex items-center justify-center ${cfg.iconBg}`}>
                <Icon size={15} className={cfg.iconColor} />
              </span>
              <p className="text-sm text-slate-700 flex-1 pt-0.5">{t.message}</p>
              <button
                onClick={() => dismiss(t.id)}
                className="text-slate-300 hover:text-slate-500 text-xs pt-1"
                aria-label="Dismiss"
              >
                ✕
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within ToastProvider");
  return ctx;
}
