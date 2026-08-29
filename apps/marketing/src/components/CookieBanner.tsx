"use client";

import { useState, useEffect } from "react";
import { enableAnalytics, hasAnalytics, track } from "@/lib/analytics";

export default function CookieBanner() {
  const [visible, setVisible] = useState(false);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    // No analytics configured → no banner needed (nothing to consent to).
    if (!hasAnalytics()) return;
    const choice = localStorage.getItem("cookies-choice");
    if (!choice) {
      setVisible(true);
      requestAnimationFrame(() => setMounted(true));
    }
  }, []);

  const choose = (granted: boolean) => {
    setMounted(false);
    setTimeout(() => {
      localStorage.setItem("cookies-choice", granted ? "accepted" : "declined");
      if (granted) {
        enableAnalytics();
        track("consent_granted");
      }
      setVisible(false);
    }, 200);
  };

  if (!visible) return null;

  return (
    <div className="fixed bottom-0 left-0 z-50 p-4">
      <div
        className="glass rounded-xl p-4 max-w-sm flex items-center gap-3 transition-all duration-250"
        style={{
          opacity: mounted ? 1 : 0,
          transform: mounted ? "translateY(0)" : "translateY(16px)",
          transitionTimingFunction: "cubic-bezier(0.23, 1, 0.32, 1)",
        }}
      >
        <p className="text-sm text-[var(--muted)] flex-1">
          We use analytics cookies to understand how visitors use the site.
        </p>
        <div className="flex items-center gap-2">
          <button
            onClick={() => choose(false)}
            className="px-3 py-1.5 text-sm text-[var(--muted)] hover:text-white transition-colors duration-150"
          >
            Decline
          </button>
          <button
            onClick={() => choose(true)}
            className="px-4 py-1.5 text-sm font-medium bg-[var(--accent)] text-white rounded-lg hover:bg-[var(--accent-hover)] transition-colors duration-150 btn-press"
          >
            Accept
          </button>
        </div>
      </div>
    </div>
  );
}
