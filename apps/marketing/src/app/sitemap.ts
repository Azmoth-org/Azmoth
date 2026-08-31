import type { MetadataRoute } from "next";

import de from "../../messages/de.json";
import { hasPlaceholder } from "@/lib/legal";
import { absoluteUrl } from "@/lib/seo";
import { routes } from "@/lib/site";

/**
 * One entry per public page. Single-locale, so no locale prefix and no alternates.
 *
 * The paths come from `routes` rather than a second hand-kept list — a renamed page that
 * leaves a stale sitemap entry behind is a 404 served to a crawler.
 *
 * The one exception is the pair of legal pages while they are still drafts. Those render
 * `noindex` for as long as `messages/de.json` carries an unfilled placeholder, and
 * submitting a URL in a sitemap while telling the crawler not to index it is a
 * contradiction Search Console reports as an error. One condition drives both, so they
 * cannot disagree: fill the details in, and the pages start being indexed *and* listed.
 */
const DRAFT_WHILE_INCOMPLETE: Record<string, unknown> = {
  [routes.impressum]: de.impressum.abschnitte,
  [routes.datenschutz]: de.datenschutz.abschnitte,
};

export default function sitemap(): MetadataRoute.Sitemap {
  const lastModified = new Date();

  return Object.values(routes)
    .filter((path) => !hasPlaceholder(DRAFT_WHILE_INCOMPLETE[path]))
    .map((path) => ({
      url: absoluteUrl(path),
      lastModified,
      changeFrequency: "monthly" as const,
      priority: path === routes.home ? 1 : 0.8,
    }));
}
