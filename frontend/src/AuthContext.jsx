import { createContext, useContext, useState, useCallback, useEffect } from "react";

/**
 * AuthContext
 *
 * Wraps your app once at the root:
 *   <AuthProvider><App /></AuthProvider>
 *
 * Provides:
 *   - user            current user object (or null)
 *   - login(email, password)
 *   - register(payload)
 *   - logout()
 *   - authFetch(url, options)   fetch() wrapper that attaches the Bearer token
 *
 * IMPORTANT: swap the other components' bare `fetch(...)` calls (in
 * InspectionChecklist.jsx, MaintenanceTickets.jsx, AICopilot.jsx, Dashboard.jsx)
 * for `authFetch(...)` from this context — otherwise their requests won't
 * carry a token and staff-only routes will 401.
 */

import { API_BASE } from "./config";

const TOKEN_KEY = "rentflow_token";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY));
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const authFetch = useCallback(
    (url, options = {}) => {
      const headers = { ...(options.headers || {}) };
      if (token) headers.Authorization = `Bearer ${token}`;
      return fetch(url, { ...options, headers });
    },
    [token]
  ); 

  const fetchMe = useCallback(async () => {
    if (!token) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      const res = await authFetch(`${API_BASE}/auth/me`);
      if (!res.ok) throw new Error("Session expired");
      setUser(await res.json());
    } catch {
      setToken(null);
      localStorage.removeItem(TOKEN_KEY);
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, [token, authFetch]);

  useEffect(() => {
    fetchMe();
  }, [fetchMe]);

  async function login(email, password) {
    const res = await fetch(`${API_BASE}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Login failed");
    }
    const data = await res.json();
    localStorage.setItem(TOKEN_KEY, data.accessToken);
    setToken(data.accessToken);
    setUser(data.user);
    return data.user;
  }

  async function register(payload) {
    const res = await fetch(`${API_BASE}/auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Registration failed");
    }
    const data = await res.json();
    localStorage.setItem(TOKEN_KEY, data.accessToken);
    setToken(data.accessToken);
    setUser(data.user);
    return data.user;
  }

  function logout() {
    localStorage.removeItem(TOKEN_KEY);
    setToken(null);
    setUser(null);
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout, authFetch }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
