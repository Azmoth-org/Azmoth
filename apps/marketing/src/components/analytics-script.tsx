import Script from "next/script";

import { getAnalytics } from "@/lib/analytics";

/**
 * The measurement script tag, or nothing at all.
 *
 * `strategy="afterInteractive"` rather than `beforeInteractive`: this is a pageview
 * counter, and nothing on the page waits for it. Loading it off the critical path is what
 * keeps it out of the largest-contentful-paint budget — the whole point of choosing a
 * ~1 KB cookieless counter over a tag manager.
 *
 * `defer` and `data-*` are the attribute shapes both providers document; they differ only
 * in which attribute names the site identifier goes under.
 */
export function AnalyticsScript() {
  const analytics = getAnalytics();
  if (!analytics) return null;

  return analytics.provider === "plausible" ? (
    <Script
      defer
      strategy="afterInteractive"
      src={analytics.src}
      data-domain={analytics.siteId}
    />
  ) : (
    <Script
      defer
      strategy="afterInteractive"
      src={analytics.src}
      data-website-id={analytics.siteId}
    />
  );
}
