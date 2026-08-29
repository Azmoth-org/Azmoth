import type { MetadataRoute } from "next";

import { getSiteUrl } from "@/lib/seo";

/**
 * Everything here is public and meant to be indexed. The application lives on a
 * different origin and serves its own robots.txt, so there is nothing to exclude.
 */
export default function robots(): MetadataRoute.Robots {
  return {
    rules: { userAgent: "*", allow: "/" },
    sitemap: `${getSiteUrl()}/sitemap.xml`,
    host: getSiteUrl(),
  };
}
