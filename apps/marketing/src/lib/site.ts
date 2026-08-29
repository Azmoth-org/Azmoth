/**
 * The handful of facts every page needs about Azmoth, in one place.
 *
 * `appUrl` is the important one: this site's entire job is to hand a visitor to the
 * product, and the product lives in a different Next application (`apps/web`) on a
 * different origin. Hard-coding that origin in a dozen `<Link href>` attributes is
 * how a marketing site ends up pointing at localhost in production, so every
 * "Anmelden" and "Kostenlos testen" resolves through here instead.
 */

/** Where `apps/web` is served. Overridden per deployment; dev default matches `pnpm dev`. */
export const appUrl = process.env.NEXT_PUBLIC_APP_URL ?? "http://localhost:3000";

/** A path inside the product app, as an absolute URL. */
export function appHref(path: string): string {
  return new URL(path, appUrl).toString();
}

export const siteConfig = {
  name: "Azmoth",
  /** Used as the <title> suffix and in structured data. */
  tagline: "GOÄ-Kodierung und Rechnungsprüfung",
  description:
    "Azmoth liest Ihre Behandlungsdokumentation, schlägt die passenden GOÄ-Ziffern vor " +
    "und begründet jede einzelne davon — nachvollziehbar, prüffest und in Sekunden.",
  /** Product entry points, resolved against `appUrl`. */
  login: appHref("/login"),
  signup: appHref("/signup"),
} as const;

/** Marketing routes, so a rename is one edit rather than a grep. */
export const routes = {
  home: "/",
  funktionen: "/funktionen",
  ueberUns: "/ueber-uns",
  faq: "/faq",
  kontakt: "/kontakt",
  datenschutz: "/datenschutz",
  agb: "/agb",
} as const;
