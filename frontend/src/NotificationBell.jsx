import { useState, useEffect, useCallback, useRef } from "react";
import { useAuth } from "./AuthContext";
import { API_BASE } from "./config";


const TYPE_ICON = {
  urgent_ticket: "🚨",
  vendor_assigned: "🔧",
  payment_received: "💰",
  ai_action_suggested: "✨",
  lease_expiring: "📄",
  general: "🔔",
};

function timeAgo(iso) {
  const diffMs = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

/**
 * NotificationBell
 *
 * A "Notify"-style notification center: badge with unread count, dropdown
 * panel listing recent notifications, click-to-mark-read. Polls for new
 * notifications every 30s — swap for websockets/SSE if you want real-time
 * push instead of polling.
 */
export default function NotificationBell() {
  const [open, setOpen] = useState(false);
  const [notifications, setNotifications] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const containerRef = useRef(null);
  const { authFetch } = useAuth();

  const fetchUnreadCount = useCallback(async () => {
    try {
      const res = await authFetch(`${API_BASE}/notifications/unread-count`);
      if (res.ok) setUnreadCount((await res.json()).count);
    } catch {
      /* silent — a failed poll shouldn't disrupt the UI */
    }
  }, [authFetch]);

  const fetchNotifications = useCallback(async () => {
    setLoading(true);
    try {
      const res = await authFetch(`${API_BASE}/notifications`);
      if (res.ok) setNotifications((await res.json()).notifications);
    } finally {
      setLoading(false);
    }
  }, [authFetch]);

  useEffect(() => {
    fetchUnreadCount();
    const interval = setInterval(fetchUnreadCount, 30000);
    return () => clearInterval(interval);
  }, [fetchUnreadCount]);

  useEffect(() => {
    if (open) fetchNotifications();
  }, [open, fetchNotifications]);

  useEffect(() => {
    function handleClickOutside(e) {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  async function markRead(id) {
    setNotifications((prev) => prev.map((n) => (n.id === id ? { ...n, read: true } : n)));
    setUnreadCount((c) => Math.max(0, c - 1));
    try {
      await authFetch(`${API_BASE}/notifications/${id}/read`, { method: "PATCH" });
    } catch {
      fetchNotifications();
    }
  }

  async function markAllRead() {
    setNotifications((prev) => prev.map((n) => ({ ...n, read: true })));
    setUnreadCount(0);
    try {
      await authFetch(`${API_BASE}/notifications/read-all`, { method: "PATCH" });
    } catch {
      fetchNotifications();
    }
  }

  return (
    <div className="relative" ref={containerRef}>
      <button
        onClick={() => setOpen((o) => !o)}
        className="relative p-2 rounded-full hover:bg-white/10 text-white"
        aria-label="Notifications"
      >
        🔔
        {unreadCount > 0 && (
          <span className="absolute -top-0.5 -right-0.5 bg-rose-500 text-white text-[10px] font-bold rounded-full min-w-[16px] h-4 flex items-center justify-center px-1">
            {unreadCount > 9 ? "9+" : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 mt-2 w-80 bg-white border border-slate-200 rounded-xl shadow-lg z-50 text-slate-900">
          <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100">
            <h3 className="text-sm font-semibold">Notifications</h3>
            {unreadCount > 0 && (
              <button onClick={markAllRead} className="text-[11px] text-indigo-600 hover:underline">
                Mark all read
              </button>
            )}
          </div>

          <div className="max-h-96 overflow-y-auto">
            {loading && <p className="text-xs text-slate-400 text-center py-6">Loading…</p>}
            {!loading && notifications.length === 0 && (
              <p className="text-xs text-slate-400 text-center py-6">No notifications yet.</p>
            )}
            {notifications.map((n) => (
              <button
                key={n.id}
                onClick={() => !n.read && markRead(n.id)}
                className={`w-full text-left px-4 py-3 border-b border-slate-50 hover:bg-slate-50 flex gap-2.5 ${
                  !n.read ? "bg-indigo-50/40" : ""
                }`}
              >
                <span className="text-base leading-none mt-0.5">{TYPE_ICON[n.type] || "🔔"}</span>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5">
                    <span className="text-xs font-semibold truncate">{n.title}</span>
                    {!n.read && <span className="w-1.5 h-1.5 rounded-full bg-indigo-500 shrink-0" />}
                  </div>
                  <p className="text-xs text-slate-500 mt-0.5 line-clamp-2">{n.body}</p>
                  <p className="text-[10px] text-slate-400 mt-1">{timeAgo(n.createdAt)}</p>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
