"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";

import { Button } from "@workspace/ui/components/button";

import { Link } from "@/i18n/navigation";
import { enableAnalytics, hasAnalytics } from "@/lib/analytics";
import { routes } from "@/lib/site";

const STORAGE_KEY = "azmoth-cookie-consent";

/**
 * Consent gate for GA4.
 *
 * Nothing measuring anything loads before "Akzeptieren" is clicked — `enableAnalytics`
 * is what injects the gtag script, and it is called from exactly two places: here, on
 * accept, and here, on mount when a previous accept is still in `localStorage`.
 * Declining stores the decision so the banner does not ask again.
 *
 * The banner hides itself entirely when `NEXT_PUBLIC_GA_MEASUREMENT_ID` is unset,
 * because a site that sets no cookies has nothing to ask permission for.
 */
export function CookieBanner() {
  const t = useTranslations("cookies");
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (!hasAnalytics()) return;

    let stored: string | null = null;
    try {
      stored = localStorage.getItem(STORAGE_KEY);
    } catch {
      // Private mode or blocked storage: ask again rather than assume consent.
    }

    if (stored === "accepted") {
      enableAnalytics();
      return;
    }
    if (stored === "declined") return;

    /*
     * The decision lives in `localStorage`, which the server cannot read. Computing
     * it during render would make the first client render disagree with the server
     * HTML and break hydration, so reading it after mount is the only correct order
     * — the banner is deliberately absent from the server output.
     */
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setVisible(true);
  }, []);

  function decide(choice: "accepted" | "declined") {
    try {
      localStorage.setItem(STORAGE_KEY, choice);
    } catch {
      // A refused write must not stop the banner from closing.
    }
    if (choice === "accepted") enableAnalytics();
    setVisible(false);
  }

  if (!visible) return null;

  return (
    <div
      role="dialog"
      aria-live="polite"
      aria-label={t("titel")}
      className="fixed inset-x-4 bottom-4 z-50 mx-auto max-w-2xl rounded-2xl border border-border bg-card p-4 shadow-lg sm:p-5"
    >
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
        <p className="flex-1 text-sm text-muted-foreground">
          {t("text")}{" "}
          <Link href={routes.datenschutz} className="underline underline-offset-3">
            {t("mehr")}
          </Link>
        </p>
        <div className="flex shrink-0 gap-2">
          <Button variant="outline" size="sm" onClick={() => decide("declined")}>
            {t("ablehnen")}
          </Button>
          <Button size="sm" onClick={() => decide("accepted")}>
            {t("akzeptieren")}
          </Button>
        </div>
      </div>
    </div>
  );
}
