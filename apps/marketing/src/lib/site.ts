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
 * Where every product-app handoff sends a visitor to book a call instead, for as long as there is
 * no partner pipeline and no hosted app to send them to. Same idea, and the same variable, as
 * `apps/web/lib/site.ts` and `apps/docs/lib/site.ts`.
 */
export function getCalComUrl(): string {
  return process.env.NEXT_PUBLIC_CAL_COM_URL ?? "https://cal.com/azmoth";
}

/**
 * The product entry points every page links to. Server-side only.
 *
 * All three currently resolve to the Cal.com link, not the app. `demo` used to be the one a
 * stranger could actually use — no account, no upload, the real engine on a synthetic delivery —
 * which is why the hero's primary call to action pointed here instead of at `signup`. That
 * reasoning holds again once the app is hosted somewhere other than `getAppUrl()`'s
 * `localhost:3000` fallback; until then, sending a visitor to a login screen or a demo on a
 * machine that is not listening is a worse first impression than a booking page. Swap the three
 * bodies back to `appHref(...)` when that changes — the callers below don't.
 */
export function getProductLinks() {
  const calCom = getCalComUrl();
  return {
    login: calCom,
    signup: calCom,
    demo: calCom,
  };
}

export const siteConfig = {
  name: "Azmoth",
  title: "Azmoth – Deterministische GOÄ-Prüfengine",
  description:
    "Mathematisch beweisbare GOÄ-Abrechnungsprüfung. Keine Blackbox-KI. " +
    "100 % nachvollziehbare Befunde mit gesetzlichen Grundlagen.",
  /** Short form, for the footer and the web app manifest. */
  tagline: "Deterministische GOÄ-Prüfengine",
  /*
   * The public mailbox. It is the same address on the contact page, in the footer, in
   * the Impressum and in the AVV, because a visitor who finds three different ones
   * concludes — correctly — that nobody is reading any of them.
   */
  email: "contact@azmoth.com",
} as const;

/**
 * Marketing routes, so a rename is one edit rather than a grep.
 *
 * `api: "/api-dokumentation"` used to be here. It is gone, and deliberately not replaced by a
 * redirect: the documentation now lives on its own origin under `apps/docs`, and a redirect
 * would keep this site's sitemap and the crawler's index pointing at a URL that is no longer
 * this site's to serve. The route 404s, `getDocsUrl()` below is what the header and footer link,
 * and the new origin publishes its own sitemap.
 */
export const routes = {
  home: "/",
  funktionen: "/funktionen",
  ueberUns: "/ueber-uns",
  faq: "/faq",
  kontakt: "/kontakt",
  impressum: "/impressum",
  datenschutz: "/datenschutz",
} as const;

/**
 * The documentation site — a separate Next application on a separate origin, exactly as the
 * product app is, and read from the environment for the same reason.
 *
 * Server-side only, and resolved at BUILD time like everything else here, because every page on
 * this site is statically prerendered. `NEXT_PUBLIC_DOCS_URL` rather than a bare `DOCS_URL`
 * because unlike `APP_URL` this one is also read by `apps/docs` itself, where it is genuinely
 * public; one variable name across both deployments is worth more than keeping four bytes out
 * of a bundle it never reaches — `SiteShell` passes it to the header as a prop.
 */
export function getDocsUrl(): string {
  return process.env.NEXT_PUBLIC_DOCS_URL ?? "https://docs.azmoth.com";
}

/*
 * `apiDocsUrl` and `apiSchemaUrl` used to be here — `https://api.azmoth.com/docs` and
 * `/openapi.json`, linked from the header, the footer and the developer section.
 *
 * They are gone because **`api.azmoth.com` has no DNS record.** Not a 404 on a live host: the
 * name does not resolve, so every one of those links ended in a browser-level connection error.
 * The reasoning that put them here was sound — `infra/docker/Caddyfile` does publish `/docs` and
 * `/openapi.json`, and pointing at a public schema beats pointing at a private repository — but
 * it described a deployment that does not exist yet.
 *
 * Linking a host that does not resolve is worse than linking nothing at all, and on this site it
 * is worse than usual: the section it sat in argues that the contract is public and checkable, so
 * the one link a technical evaluator is most likely to click was also the one that proved the
 * opposite. `docs.azmoth.com` is live and says what the API is; that is what the developer track
 * points at now.
 *
 * Put them back when the host answers, not before.
 */
