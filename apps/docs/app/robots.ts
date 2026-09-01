import type { MetadataRoute } from "next";

import { absoluteUrl } from "@/lib/site";

/**
 * Documentation is meant to be found, so everything is crawlable except the search index —
 * `/api/search` returns the same content the pages already expose, in a shape no reader wants
 * as a result.
 */
export default function robots(): MetadataRoute.Robots {
  return {
    rules: { userAgent: "*", allow: "/", disallow: "/api/" },
    sitemap: absoluteUrl("/sitemap.xml"),
  };
}
