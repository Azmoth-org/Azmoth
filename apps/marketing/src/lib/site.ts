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

/**
 * The product entry points every page links to. Server-side only.
 *
 * `demo` is the one a stranger can actually use, and it is why the hero's primary call to action
 * no longer points at `signup`. Registration is gated by `SIGNUP_ALLOWLIST` in the product app, so
 * a "Kostenlos testen" button aimed there sends most visitors to a form that refuses them — which
 * is a worse first impression than not offering it. `/demo` needs no account, takes no upload and
 * shows the real engine on a synthetic delivery; `signup` stays as the deliberate second step for
 * somebody who wants their own data audited.
 */
export function getProductLinks() {
  return {
    login: appHref("/login"),
    signup: appHref("/signup"),
    demo: appHref("/demo"),
  };
}

export const siteConfig = {
  name: "Azmoth",
  title: "Azmoth – Deterministische GOÄ-Prüfengine",
  description:
    "Mathematisch beweisbare GOÄ-Abrechnungsprüfung. Keine Blackbox-KI. " +
    "100 % nachvollziehbare Befunde mit gesetzlichen Grundlagen.",
  /** Short form, for the footer and the web app manifest. */
  tagline: "Deterministische GOÄ-Prüfengine",
  /*
   * The public mailbox. It is the same address on the contact page, in the footer, in
   * the Impressum and in the AVV, because a visitor who finds three different ones
   * concludes — correctly — that nobody is reading any of them.
   */
  email: "kontakt@azmoth.com",
  /** Where the partner API contract and the anonymisation script live. */
  github: "https://github.com/oussamakhadraoui/azmoth",
} as const;

/** Marketing routes, so a rename is one edit rather than a grep. */
export const routes = {
  home: "/",
  funktionen: "/funktionen",
  ueberUns: "/ueber-uns",
  faq: "/faq",
  kontakt: "/kontakt",
  api: "/api-dokumentation",
  impressum: "/impressum",
  datenschutz: "/datenschutz",
} as const;

/**
 * The partner API contract, in the repository.
 *
 * `/api-dokumentation` on this site is the orientation page — what the API is, one
 * runnable call, and the constraints an integrator needs before they read anything
 * else. The contract itself is `docs/api/PARTNER_API.md`, which is versioned with the
 * engine that implements it. Publishing a second copy here is how the two disagree by
 * the third release, so the page links out rather than restating it.
 */
export const apiContractUrl =
  "https://github.com/oussamakhadraoui/azmoth/blob/main/docs/api/PARTNER_API.md";
