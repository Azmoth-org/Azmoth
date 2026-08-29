"use client";

import { useEffect, useMemo } from "react";
import { useTranslations } from "next-intl";
import { usePathname } from "@/i18n/navigation";
import { animatePageIn } from "@/lib/pageTransition";

/** Routes where the marketing page transition must NOT fire. */
const BARE_PATHS = ["/login", "/forgot-password", "/reset-password", "/magic-link", "/dashboard", "/agency", "/admin", "/client"];

/**
 * Page-name config for the transition-overlay reveal (silklearn PAGE_ROUTES
 * pattern). Values are `navigation` message keys, so the revealed name is
 * localized. Nested routes (services/[slug], blog/[slug], …) fall back to
 * their parent's name via prefix matching. Routes not listed here fall back
 * to a humanized URL segment (see fallbackPageName) — the reveal is never
 * empty, so new/dynamic pages can't break it.
 */
const PAGE_ROUTES = {
  "/": "logo",
  "/products": "products",
  "/services": "services",
  "/blog": "blog",
  "/about": "about",
  "/faq": "faq",
  "/contact": "contact",
  "/intake": "intake",
  "/privacy": "privacy",
  "/terms": "terms",
} as const;

type PageRouteKey = (typeof PAGE_ROUTES)[keyof typeof PAGE_ROUTES];

function resolvePageName(pathname: string): PageRouteKey | undefined {
  const direct = Object.entries(PAGE_ROUTES).find(([route]) => route === pathname);
  if (direct) return direct[1];

  const parent = Object.entries(PAGE_ROUTES).find(
    ([route]) => route !== "/" && pathname.startsWith(`${route}/`),
  );
  return parent?.[1];
}

/**
 * Last-resort title for routes not in PAGE_ROUTES (e.g. a page added later
 * without a config entry): humanize the final path segment, so
 * "/some-new-page" → "Some New Page".
 */
function fallbackPageName(pathname: string): string {
  const seg = pathname.split("/").filter(Boolean).pop() ?? "";
  return seg
    .split("-")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

/**
 * Route template — remounts on every navigation. Fires the marketing
 * page-in curve only on the site pages; auth + app routes render bare.
 * (Uses the i18n usePathname — locale-stripped — so /en/dashboard
 * matches "/dashboard".)
 */
export default function Template({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const t = useTranslations("navigation");
  const isBare = BARE_PATHS.some((p) => pathname === p || pathname.startsWith(`${p}/`));

  const pageName = useMemo(() => {
    const key = resolvePageName(pathname);
    return key ? t(key) : fallbackPageName(pathname);
  }, [pathname, t]);

  useEffect(() => {
    if (isBare) return;
    const el = document.getElementById("page-name-text");
    if (el) el.textContent = pageName;
    animatePageIn();
  }, [isBare, pageName]);

  return <>{children}</>;
}
