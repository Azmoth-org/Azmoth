"use client";

import { useCallback, useEffect, useState } from "react";

export type Theme = "light" | "dark";

const STORAGE_KEY = "silkdev-theme";

/** Stored theme (defaults to dark — the site's brand palette). */
export function getStoredTheme(): Theme {
  if (typeof window === "undefined") return "dark";
  return localStorage.getItem(STORAGE_KEY) === "light" ? "light" : "dark";
}

/**
 * Applies the theme by toggling `light` on <html>. The portal reads the
 * :root tokens (flip with the class); marketing + auth trees are re-guarded
 * dark via `.site-dark` in AppShell.
 */
export function applyTheme(theme: Theme) {
  document.documentElement.classList.toggle("light", theme === "light");
}

/** Portal theme hook: current theme + toggle (persisted to localStorage). */
export function useTheme() {
  const [theme, setTheme] = useState<Theme>("dark");

  useEffect(() => {
    const stored = getStoredTheme();
    setTheme(stored);
    applyTheme(stored);
  }, []);

  const toggle = useCallback(() => {
    setTheme((prev) => {
      const next: Theme = prev === "light" ? "dark" : "light";
      localStorage.setItem(STORAGE_KEY, next);
      applyTheme(next);
      return next;
    });
  }, []);

  return { theme, toggle };
}
