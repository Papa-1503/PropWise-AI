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
 *   - properties           staff-only: list of all buildings [{id, name}], for the
 *                          building selector and for looking up a building's name
 *                          from a propertyId when displaying tickets/charges/etc.
 *   - selectedProperty     the currently active building context, {id, name} | null.
 *                          null means "All Buildings" (portfolio-wide view).
 *   - setSelectedProperty  updates the selection, persisted to localStorage so it
 *                          survives a page reload
 *   - getPropertyName(id)  looks up a building's display name from its propertyId —
 *                          use this anywhere a ticket/charge/lease shows "Unit X" so
 *                          it can also show which building that unit belongs to.
 *                          Multiple buildings can share the same unit number, so
 *                          unitId alone is never enough to identify a unit.
 *
 * IMPORTANT: swap the other components' bare `fetch(...)` calls (in
 * InspectionChecklist.jsx, MaintenanceTickets.jsx, AICopilot.jsx, Dashboard.jsx)
 * for `authFetch(...)` from this context — otherwise their requests won't
 * carry a token and staff-only routes will 401.
 */

import { API_BASE } from "./config";

const TOKEN_KEY = "rentflow_token";
const SELECTED_PROPERTY_KEY = "rentflow_selected_property";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY));
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [properties, setProperties] = useState([]);
  const [selectedProperty, setSelectedPropertyState] = useState(() => {
    try {
      const saved = localStorage.getItem(SELECTED_PROPERTY_KEY);
      return saved ? JSON.parse(saved) : null;
    } catch {
      return null;
    }
  });

  const authFetch = useCallback(
    (url, options = {}) => {
      const headers = { ...(options.headers || {}) };
      if (token) headers.Authorization = `Bearer ${token}`;
      // credentials: "include" makes the browser also send the real
      // HttpOnly session cookie set by login/register (backend/auth.py,
      // this session's earlier work) on every request - the Bearer
      // header above is left completely unchanged and still sent
      // alongside it, so this is purely additive, not a replacement.
      // get_current_user already accepts either credential source; this
      // is what makes the frontend actually offer the cookie at all,
      // rather than the safer path existing on the backend with no way
      // for the browser to use it.
      return fetch(url, { ...options, headers, credentials: "include" });
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

  // Staff can see every building, so load the full list once they're logged
  // in — used for the building selector dropdown and for looking up a
  // building's name anywhere a unit is shown, so "Unit 101" never appears
  // without saying which building it's in.
  const fetchProperties = useCallback(async () => {
    if (!token || user?.role !== "staff") {
      setProperties([]);
      return;
    }
    try {
      const res = await authFetch(`${API_BASE}/properties`);
      if (!res.ok) return;
      const data = await res.json();
      const list = (data.properties || []).map((p) => ({ id: p.id, name: p.name }));
      setProperties(list);
    } catch {
      // fail quietly — the building selector just won't populate; existing
      // "All Buildings" behavior still works via propertyId=null
    }
  }, [token, user, authFetch]);

  useEffect(() => {
    fetchProperties();
  }, [fetchProperties]);

  function setSelectedProperty(prop) {
    setSelectedPropertyState(prop);
    if (prop) {
      localStorage.setItem(SELECTED_PROPERTY_KEY, JSON.stringify(prop));
    } else {
      localStorage.removeItem(SELECTED_PROPERTY_KEY);
    }
  }

  function getPropertyName(propertyId) {
    if (!propertyId) return null;
    const match = properties.find((p) => p.id === propertyId);
    return match ? match.name : propertyId;
  }

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
    // The real HttpOnly cookie (backend/auth.py, this session) can't be
    // cleared from JavaScript at all - that's the entire point of
    // HttpOnly. Without this call, clearing localStorage alone would
    // leave a real, still-valid 7-day session cookie active on this
    // browser even after "logging out." Fire-and-forget: even if this
    // request fails (offline, etc.), the local token/state is still
    // cleared below, so the user is genuinely logged out of this
    // browser's own view of the app either way.
    fetch(`${API_BASE}/auth/logout`, { method: "POST", credentials: "include" }).catch(() => {});
    localStorage.removeItem(TOKEN_KEY);
    setToken(null);
    setUser(null);
    setProperties([]);
    setSelectedPropertyState(null);
  }

  return (
    <AuthContext.Provider
      value={{
        user,
        setUser,
        loading,
        login,
        register,
        logout,
        authFetch,
        properties,
        selectedProperty,
        setSelectedProperty,
        getPropertyName,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
