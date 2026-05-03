"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import React from "react";

export interface ThemeDefinition {
  id: string;
  name: string;
  icon: string;
  variables: {
    "--theme-bg": string;
    "--theme-fg": string;
    "--theme-surface": string;
    "--theme-muted": string;
    "--theme-border": string;
    "--theme-accent": string;
    "--theme-input-bg": string;
    "--theme-sidebar-bg": string;
  };
}

export const THEMES: ThemeDefinition[] = [
  {
    id: "midnight",
    name: "Midnight",
    icon: "🌙",
    variables: {
      "--theme-bg": "#000000",
      "--theme-fg": "#FFFFFF",
      "--theme-surface": "#001f3f",
      "--theme-muted": "#AAAAAA",
      "--theme-border": "rgba(170,170,170,0.2)",
      "--theme-accent": "#001f3f",
      "--theme-input-bg": "#0d1117",
      "--theme-sidebar-bg": "rgba(0,31,63,0.5)",
    },
  },
  {
    id: "ocean",
    name: "Ocean",
    icon: "🌊",
    variables: {
      "--theme-bg": "#0f172a",
      "--theme-fg": "#e2e8f0",
      "--theme-surface": "#1e293b",
      "--theme-muted": "#94a3b8",
      "--theme-border": "rgba(148,163,184,0.2)",
      "--theme-accent": "#1e40af",
      "--theme-input-bg": "#1e293b",
      "--theme-sidebar-bg": "rgba(30,41,59,0.8)",
    },
  },
  {
    id: "forest",
    name: "Forest",
    icon: "🌲",
    variables: {
      "--theme-bg": "#0a1612",
      "--theme-fg": "#d1fae5",
      "--theme-surface": "#064e3b",
      "--theme-muted": "#6ee7b7",
      "--theme-border": "rgba(110,231,183,0.15)",
      "--theme-accent": "#065f46",
      "--theme-input-bg": "#0d2818",
      "--theme-sidebar-bg": "rgba(6,78,59,0.5)",
    },
  },
  {
    id: "light",
    name: "Light",
    icon: "☀️",
    variables: {
      "--theme-bg": "#f8fafc",
      "--theme-fg": "#0f172a",
      "--theme-surface": "#e2e8f0",
      "--theme-muted": "#64748b",
      "--theme-border": "rgba(100,116,139,0.25)",
      "--theme-accent": "#001f3f",
      "--theme-input-bg": "#ffffff",
      "--theme-sidebar-bg": "rgba(226,232,240,0.9)",
    },
  },
];

const STORAGE_KEY = "ideaflow-theme";

interface ThemeContextValue {
  theme: ThemeDefinition;
  setTheme: (themeId: string) => void;
  themes: ThemeDefinition[];
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

function applyTheme(theme: ThemeDefinition) {
  const root = document.documentElement;
  for (const [key, value] of Object.entries(theme.variables)) {
    root.style.setProperty(key, value);
  }
  // Set data-theme attribute for CSS overrides (light vs dark)
  root.setAttribute("data-theme", theme.id);
  // Update color-scheme for browser UI (scrollbars, form controls)
  root.style.colorScheme = theme.id === "light" ? "light" : "dark";
}

function getInitialThemeId(): string {
  if (typeof window === "undefined") return "midnight";
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored && THEMES.some((t) => t.id === stored)) {
      return stored;
    }
  } catch {
    // localStorage not available
  }
  return "midnight";
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [themeId, setThemeId] = useState<string>(getInitialThemeId);

  const currentTheme = THEMES.find((t) => t.id === themeId) ?? THEMES[0];

  useEffect(() => {
    applyTheme(currentTheme);
  }, [currentTheme]);

  const setTheme = useCallback((id: string) => {
    const found = THEMES.find((t) => t.id === id);
    if (!found) return;
    setThemeId(id);
    try {
      localStorage.setItem(STORAGE_KEY, id);
    } catch {
      // localStorage not available
    }
  }, []);

  const value: ThemeContextValue = {
    theme: currentTheme,
    setTheme,
    themes: THEMES,
  };

  return React.createElement(ThemeContext.Provider, { value }, children);
}

export function useTheme(): ThemeContextValue {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error("useTheme must be used within a ThemeProvider");
  }
  return context;
}
