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

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  // Use lazy initializer to avoid setState in effect
  const [theme, setThemeState] = useState<Theme>(() => {
    if (typeof window === "undefined") return "dark";
    const stored = localStorage.getItem(STORAGE_KEY) as Theme | null;
    return stored && ["dark", "light", "system"].includes(stored)
      ? stored
      : "dark";
  });
  const [mounted, setMounted] = useState(false);
  // Counter to trigger re-render when system theme changes
  const [systemThemeKey, setSystemThemeKey] = useState(0);

  // Use useMemo instead of useState + useEffect for resolved theme
  const resolvedTheme = useMemo<ResolvedTheme>(() => {
    if (!mounted) return "dark";
    // systemThemeKey triggers recalculation when system theme changes
    void systemThemeKey;
    return theme === "system" ? getSystemTheme() : theme;
  }, [theme, mounted, systemThemeKey]);

  // Set mounted on client
  useEffect(() => {
    setMounted(true);
  }, []);

  // Apply theme to document when resolved theme changes
  useEffect(() => {
    if (!mounted) return;
    document.documentElement.setAttribute("data-theme", resolvedTheme);
  }, [resolvedTheme, mounted]);

  // Listen for system theme changes when in "system" mode
  useEffect(() => {
    if (theme !== "system") return;

    const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");

    const handleChange = () => {
      // Increment key to trigger useMemo recalculation
      setSystemThemeKey((k) => k + 1);
    };

    mediaQuery.addEventListener("change", handleChange);
    return () => mediaQuery.removeEventListener("change", handleChange);
  }, [theme]);

  const setTheme = (newTheme: Theme) => {
    setThemeState(newTheme);
    localStorage.setItem(STORAGE_KEY, newTheme);
  };

  // Prevent flash of wrong theme
  if (!mounted) {
    return <div style={{ visibility: "hidden" }}>{children}</div>;
  }

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
