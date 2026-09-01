"use client";

import { useEffect } from "react";
import { useTranslations } from "next-intl";

import { usePathname } from "@/i18n/navigation";
import { animatePageIn } from "@/lib/page-transition";
import { routes } from "@/lib/site";

/**
 * The half of the page transition that runs on arrival.
 *
 * A `template.tsx` rather than a `layout.tsx` because Next remounts a template on every
 * navigation and reuses a layout — an effect in the layout would fire once per session, which is
 * the wrong number for something that has to run once per route change.
 *
 * `animatePageIn` no-ops unless `animatePageOut` ran first, so this fires nothing on a cold load
 * and pulls in no GSAP chunk. See `lib/page-transition.ts`.
 */

/**
 * The name the curtain reveals, per route.
 *
 * Values are `navigation` message keys, so the label is translated rather than derived from the
 * URL slug — "ueber-uns" humanises to "Ueber Uns", with the umlaut lost, which is a detail a
 * German visitor reads as carelessness.
 *
 * Keys are the `routes` constants rather than string literals: renaming a route is already one
 * edit there, and a second copy of "/funktionen" here would silently fall through to the default
 * the day somebody changed it.
 */
const PAGE_LABELS: Record<string, string> = {
  [routes.home]: "startseite",
  [routes.funktionen]: "funktionen",
  [routes.faq]: "faq",
  [routes.ueberUns]: "ueberUns",
  [routes.kontakt]: "kontakt",
  [routes.impressum]: "impressum",
  [routes.datenschutz]: "datenschutz",
};

export default function Template({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const t = useTranslations("navigation");

  /*
   * The label is written to the DOM rather than rendered, because the node it goes into belongs to
   * the overlay in the *layout* — which must not remount between navigations, or the curtain
   * unmounts mid-sweep. This is the one place the two halves touch.
   *
   * `?? "startseite"` covers the 404 route, which has no entry: the sheet always says something.
   */
  useEffect(() => {
    const label = document.getElementById("azm-curtain-label");
    if (label) label.textContent = t(PAGE_LABELS[pathname] ?? "startseite");
    void animatePageIn();
  }, [pathname, t]);

  return <>{children}</>;
}
