"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";

type Theme = "dark" | "light" | "system";
type ResolvedTheme = "dark" | "light";

interface ThemeContextType {
  theme: Theme;
  resolvedTheme: ResolvedTheme;
  setTheme: (theme: Theme) => void;
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

const STORAGE_KEY = "story-tracking-theme";

function getSystemTheme(): ResolvedTheme {
  if (typeof window === "undefined") return "dark";
  return window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

function getInitialTheme(): Theme {
  if (typeof window === "undefined") return "dark";
  const stored = localStorage.getItem(STORAGE_KEY) as Theme | null;
  return stored && ["dark", "light", "system"].includes(stored)
    ? stored
    : "dark";
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  // Initialize with actual value (inline script already set data-theme)
  const [theme, setThemeState] = useState<Theme>(getInitialTheme);
  // Counter to trigger re-render when system theme changes
  const [systemThemeKey, setSystemThemeKey] = useState(0);

  const resolvedTheme = useMemo<ResolvedTheme>(() => {
    // systemThemeKey triggers recalculation when system theme changes
    void systemThemeKey;
    return theme === "system" ? getSystemTheme() : theme;
  }, [theme, systemThemeKey]);

  // Sync theme to document (inline script handles initial, this handles changes)
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", resolvedTheme);
  }, [resolvedTheme]);

  // Listen for system theme changes when in "system" mode
  useEffect(() => {
    if (theme !== "system") return;

    const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");

    const handleChange = () => {
      setSystemThemeKey((k) => k + 1);
    };

    mediaQuery.addEventListener("change", handleChange);
    return () => mediaQuery.removeEventListener("change", handleChange);
  }, [theme]);

  const setTheme = (newTheme: Theme) => {
    setThemeState(newTheme);
    localStorage.setItem(STORAGE_KEY, newTheme);
  };

  // No hiding - inline script in layout.tsx already set correct theme
  return (
    <ThemeContext.Provider value={{ theme, resolvedTheme, setTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  const context = useContext(ThemeContext);
  if (context === undefined) {
    throw new Error("useTheme must be used within a ThemeProvider");
  }
  return context;
}
