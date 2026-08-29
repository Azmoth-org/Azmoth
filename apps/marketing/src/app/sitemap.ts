import type { MetadataRoute } from "next";

import { absoluteUrl } from "@/lib/seo";
import { routes } from "@/lib/site";

/**
 * One entry per public page. Single-locale, so no locale prefix and no alternates.
 *
 * The paths come from `routes` rather than a second hand-kept list — a renamed page
 * that leaves a stale sitemap entry behind is a 404 served to a crawler.
 */
export default function sitemap(): MetadataRoute.Sitemap {
  const lastModified = new Date();

  return Object.values(routes).map((path) => ({
    url: absoluteUrl(path),
    lastModified,
    changeFrequency: "monthly" as const,
    priority: path === routes.home ? 1 : 0.8,
  }));
}
