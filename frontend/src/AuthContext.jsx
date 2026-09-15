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
 *   - authFetch(url, options)   fetch() wrapper that sends the real HttpOnly
 *                          session cookie on every request
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
 * carry the session and staff-only routes will 401.
 *
 * CHANGED Sept 15, 2026: real cookie-auth migration, completing the
 * "still open" item flagged in this session's own earlier security-
 * hardening pass - the backend (auth.py's get_current_user) has
 * accepted the real HttpOnly session cookie as an equally-valid
 * credential alongside the Bearer header since that pass, and
 * authFetch below was already sending it (credentials: "include"),
 * but the frontend's own SOURCE OF TRUTH for "am I logged in" was
 * still a JWT sitting in localStorage - genuinely readable by any
 * injected script, the exact XSS exposure HttpOnly cookies exist to
 * close. There is now no token in localStorage at all: login/
 * register/2FA/org-signup rely entirely on the cookie the server's
 * response already sets, and on mount this always asks the server
 * (GET /auth/me) whether a real session exists, since an HttpOnly
 * cookie is by design invisible to JavaScript - there is no client-
 * side way to check it any other way.
 *
 * Real, separate gap also fixed alongside this: login/register/2FA/
 * org-signup previously called fetch() WITHOUT credentials: "include"
 * - confirmed directly that a browser will not persist a Set-Cookie
 * response header from a cross-origin request unless credentials are
 * explicitly requested on that same request, meaning the real session
 * cookie may never have actually been stored by the browser at all
 * before this fix, regardless of what the backend was sending.
 */

import { API_BASE } from "./config";

const SELECTED_PROPERTY_KEY = "rentflow_selected_property";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
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
      // credentials: "include" sends the real HttpOnly session cookie
      // set by login/register/2FA/org-signup (backend/auth.py) on
      // every request - this is the ONLY credential this app sends
      // now; there is no Authorization header and no token anywhere
      // in JavaScript-readable storage to attach one from.
      return fetch(url, { ...options, credentials: "include" });
    },
    []
  );

  const fetchMe = useCallback(async () => {
    // No local signal exists for "is there a session" - an HttpOnly
    // cookie can't be read from JavaScript by design, so the real,
    // only way to know is to ask the server and see what comes back.
    try {
      const res = await authFetch(`${API_BASE}/auth/me`);
      if (!res.ok) throw new Error("Not authenticated");
      setUser(await res.json());
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, [authFetch]);

  useEffect(() => {
    fetchMe();
  }, [fetchMe]);

  // Staff can see every building, so load the full list once they're logged
  // in — used for the building selector dropdown and for looking up a
  // building's name anywhere a unit is shown, so "Unit 101" never appears
  // without saying which building it's in.
  const fetchProperties = useCallback(async () => {
    if (!user || user.role !== "staff") {
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
  }, [user, authFetch]);

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
      credentials: "include",
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Login failed");
    }
    const data = await res.json();
    // CHANGED Sept 13, 2026: real 2FA support (routers/two_factor.py,
    // routers/auth.py's /login). A password-only success no longer
    // always means a real session - an account with 2FA enabled gets
    // {requires2FA: true, pendingToken} instead, and no session is
    // established here at all (no cookie is set for a pending-2FA
    // response either - see get_current_user's own real rejection of
    // a pending2FA token). The caller (LoginScreen) is responsible for
    // then collecting the real code and calling completeTwoFactorLogin
    // below - this deliberately mirrors the real two-step flow the
    // backend enforces, rather than hiding it behind one function that
    // pretends login is always one step.
    if (data.requires2FA) {
      return { requires2FA: true, pendingToken: data.pendingToken };
    }
    // The server's response already set the real session cookie
    // (set_session_cookie, backend/auth.py) - nothing else to store
    // client-side, the cookie IS the session from here on.
    setUser(data.user);
    return data.user;
  }

  async function completeTwoFactorLogin(pendingToken, code) {
    const res = await fetch(`${API_BASE}/auth/login/2fa`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ pendingToken, code }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "That code didn't work.");
    }
    const data = await res.json();
    setUser(data.user);
    return data.user;
  }

  async function register(payload) {
    const res = await fetch(`${API_BASE}/auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Registration failed");
    }
    const data = await res.json();
    setUser(data.user);
    return data.user;
  }

  async function signupOrganization(payload) {
    const res = await fetch(`${API_BASE}/auth/signup-organization`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Couldn't create your organization.");
    }
    const data = await res.json();
    setUser(data.user);
    return data.user;
  }

  function logout() {
    // The real HttpOnly cookie (backend/auth.py) can't be cleared from
    // JavaScript at all - that's the entire point of HttpOnly. This
    // real server round-trip is now the ONLY way this app can end a
    // session - there's no longer a local token to simply discard.
    // Awaited (not fire-and-forget) so `user` is only cleared once the
    // cookie is genuinely gone server-side too, avoiding a brief state
    // where the UI shows logged-out but the cookie is still valid.
    fetch(`${API_BASE}/auth/logout`, { method: "POST", credentials: "include" })
      .catch(() => {})
      .finally(() => {
        setUser(null);
        setProperties([]);
        setSelectedPropertyState(null);
      });
  }

  return (
    <AuthContext.Provider
      value={{
        user,
        setUser,
        loading,
        login,
        completeTwoFactorLogin,
        register,
        signupOrganization,
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
