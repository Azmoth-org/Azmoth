import type { MetadataRoute } from "next";
import { getSiteUrl } from "@/lib/seo";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      allow: "/",
      // App/portal surfaces — never index them (under every locale).
      disallow: [
        "/en/admin",
        "/fr/admin",
        "/en/dashboard",
        "/fr/dashboard",
        "/en/client",
        "/fr/client",
        "/en/agency",
        "/fr/agency",
        "/en/login",
        "/fr/login",
        "/api/",
      ],
    },
    sitemap: `${getSiteUrl()}/sitemap.xml`,
    host: getSiteUrl(),
  };
}
