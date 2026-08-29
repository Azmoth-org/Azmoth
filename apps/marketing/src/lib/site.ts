/**
 * The handful of facts every page needs about Azmoth, in one place.
 *
 * `getAppUrl()` is the important one: this site's entire job is to hand a visitor
 * to the product, and the product is a different Next application on a different
 * origin. Hard-coding that origin across a dozen `href`s is how a marketing site
 * ends up pointing at localhost in production.
 *
 * **This resolves at BUILD time for every page on this site**, because every page is
 * statically prerendered — a `process.env` read during prerender bakes its value
 * into the HTML just as surely as a `NEXT_PUBLIC_` inline does. So a deployment sets
 * it as a *build argument*, not as a container variable, and changing it means a
 * rebuild. That is the right trade for a brochure: the alternative is opting the
 * whole site out of static rendering to move one URL.
 *
 * `APP_URL` is preferred over `NEXT_PUBLIC_APP_URL` anyway, for two smaller reasons:
 * it stays out of the client bundle, and it would resolve per-request if any page
 * here ever did become dynamic. `NEXT_PUBLIC_APP_URL` is still honoured, so the
 * variable name the compose file already uses keeps working.
 *
 * Server-side only. `SiteShell` resolves it once and passes the two hrefs down to
 * the client header as props.
 */
export function getAppUrl(): string {
  return (
    process.env.APP_URL ?? process.env.NEXT_PUBLIC_APP_URL ?? "http://localhost:3000"
  );
}

/** A path inside the product app, as an absolute URL. Server-side only. */
export function appHref(path: string): string {
  return new URL(path, getAppUrl()).toString();
}

/** The two product entry points every page links to. Server-side only. */
export function getProductLinks() {
  return {
    login: appHref("/login"),
    signup: appHref("/signup"),
  };
}

export const siteConfig = {
  name: "Azmoth",
  title: "Azmoth – Deterministische GOÄ-Prüfengine",
  description:
    "Mathematische Gewissheit für die medizinische Abrechnung. Keine Blackbox, " +
    "keine KI-Halluzinationen. 100% nachvollziehbare GOÄ-Compliance.",
  /** Short form, for the footer and the web app manifest. */
  tagline: "Deterministische GOÄ-Prüfengine",
  email: "kontakt@azmoth.de",
} as const;

/** Marketing routes, so a rename is one edit rather than a grep. */
export const routes = {
  home: "/",
  funktionen: "/funktionen",
  ueberUns: "/ueber-uns",
  faq: "/faq",
  kontakt: "/kontakt",
  impressum: "/impressum",
  datenschutz: "/datenschutz",
  agb: "/agb",
} as const;
