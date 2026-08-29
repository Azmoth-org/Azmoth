"use client";

declare global {
  interface Window {
    dataLayer?: unknown[];
    gtag?: (...args: unknown[]) => void;
  }
}

const GA_ID = process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID;

/** Inject the GA4 gtag script + init. Called only after user consent. */
export function enableAnalytics() {
  if (!GA_ID || typeof window === "undefined") return;
  if (window.gtag) return; // already loaded
  try {
    const script = document.createElement("script");
    script.async = true;
    script.src = `https://www.googletagmanager.com/gtag/js?id=${GA_ID}`;
    document.head.appendChild(script);

    window.dataLayer = window.dataLayer || [];
    window.gtag = function gtag(...args: unknown[]) {
      window.dataLayer!.push(args);
    };
    window.gtag("js", new Date());
    window.gtag("config", GA_ID, { anonymize_ip: true });
  } catch {
    /* analytics must never break the funnel */
  }
}

/** Fire a GA4 event (no-op if GA isn't loaded). */
export function track(event: string, params?: Record<string, unknown>) {
  if (!GA_ID || typeof window === "undefined") return;
  try {
    if (typeof window.gtag === "function") {
      window.gtag("event", event, params ?? {});
    } else {
      window.dataLayer = window.dataLayer || [];
      window.dataLayer.push({ event, ...params });
    }
  } catch {
    /* analytics must never break the funnel */
  }
}

/** Whether GA is configured (the cookie banner hides entirely when it isn't). */
export function hasAnalytics(): boolean {
  return Boolean(GA_ID);
}
