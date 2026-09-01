/**
 * The handful of facts every page on this site needs, in one place.
 *
 * The documentation site is the third origin in the Azmoth ecosystem, and its whole navigational
 * job is to point at the other two: back to the marketing site, and out to the product. Both
 * origins are read from the environment for the same reason `apps/marketing/src/lib/site.ts`
 * does it — hard-coding them across a handful of `href`s is how a site ends up linking to
 * localhost in production.
 *
 * **These resolve at BUILD time.** Every page here is statically prerendered, so a
 * `process.env` read during prerender bakes its value into the HTML. A deployment sets these as
 * build arguments, not as container variables, and changing one means a rebuild. That is the
 * right trade for a documentation site: the alternative is opting the whole thing out of static
 * rendering to move one URL.
 */
export const siteConfig = {
  name: "Azmoth",
  title: "Azmoth-Dokumentation",
  description:
    "Dokumentation der deterministischen GOÄ-Prüfengine: Prüfablauf, Verdikte und die " +
    "Partner-API für PVS-Hersteller und Abrechnungsstellen.",
  email: "contact@azmoth.com",
} as const;

/** The marketing site. */
export function getSiteUrl(): string {
  return process.env.NEXT_PUBLIC_SITE_URL ?? "https://azmoth.com";
}

/** This site, for canonical URLs and the sitemap. */
export function getDocsUrl(): string {
  return process.env.NEXT_PUBLIC_DOCS_URL ?? "https://docs.azmoth.com";
}

/** The product application. */
export function getAppUrl(): string {
  return (
    process.env.APP_URL ?? process.env.NEXT_PUBLIC_APP_URL ?? "https://app.azmoth.com"
  );
}

export function absoluteUrl(path = "/"): string {
  return new URL(path, getDocsUrl()).toString();
}

/**
 * The machine-readable contract, and its interactive copy.
 *
 * The same two URLs the marketing site links, and for the same reason: the OpenAPI schema the
 * engine serves is by construction the one the running engine implements. The prose here
 * orients; it does not restate the contract, because two copies of one contract disagree by the
 * third release.
 */
export const apiDocsUrl = "https://api.azmoth.com/docs";
export const apiSchemaUrl = "https://api.azmoth.com/openapi.json";
