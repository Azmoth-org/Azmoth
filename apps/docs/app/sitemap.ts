import type { MetadataRoute } from "next";

import { absoluteUrl } from "@/lib/site";
import { source } from "@/lib/source";

/**
 * One entry per published page, derived from the content tree rather than a hand-kept list.
 *
 * A second list is how a renamed page leaves a stale sitemap entry behind — a 404 served to a
 * crawler. `source.getPages()` is the same call the sidebar renders from, so a page is listed
 * here exactly when it exists.
 */
export default function sitemap(): MetadataRoute.Sitemap {
  const lastModified = new Date();

  return source.getPages().map((page) => ({
    url: absoluteUrl(page.url),
    lastModified,
    changeFrequency: "monthly" as const,
    priority: page.url === "/" ? 1 : 0.8,
  }));
}
