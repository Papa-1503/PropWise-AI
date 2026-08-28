import { createContext, useContext, useState, useEffect, useCallback } from "react";

/**
 * Dark mode, persisted via localStorage — matching a design shared for
 * evaluation (Aug 26, 2026), which used the same persistence approach
 * (`localStorage.getItem('theme')`, defaulting to light) and the same
 * manual toggle model rather than only following OS preference.
 */

const STORAGE_KEY = "rentflow_theme";
const DarkModeContext = createContext(null);

export function DarkModeProvider({ children }) {
  const [dark, setDark] = useState(() => {
    try {
      return localStorage.getItem(STORAGE_KEY) === "dark";
    } catch {
      return false;
    }
  });

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
  }, [dark]);

  const toggle = useCallback(() => {
    setDark((prev) => {
      const next = !prev;
      try {
        localStorage.setItem(STORAGE_KEY, next ? "dark" : "light");
      } catch {
        // ignore — persistence is a nicety, not a requirement
      }
      return next;
    });
  }, []);

  return (
    <DarkModeContext.Provider value={{ dark, toggle }}>
      {children}
    </DarkModeContext.Provider>
  );
}

export function useDarkMode() {
  const ctx = useContext(DarkModeContext);
  if (!ctx) throw new Error("useDarkMode must be used within DarkModeProvider");
  return ctx;
}
