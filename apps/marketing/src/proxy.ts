import createMiddleware from "next-intl/middleware";

import { routing } from "./i18n/routing";

export default createMiddleware(routing);

export const config = {
  /*
   * Pages only.
   *
   * The exclusions are not decoration: anything this matcher catches is handed to
   * the locale middleware, which rewrites it under a locale prefix. `/sitemap.xml`
   * and `/robots.txt` escape via the "has a dot" clause, but `/opengraph-image` and
   * `/twitter-image` have no extension — without naming them here they were rewritten
   * to `/de/opengraph-image`, which does not exist, and every social preview 404'd.
   *
   * **`api/` carries its trailing slash on purpose.** As a bare `api` this is a prefix
   * match, so it swallowed every path merely *beginning* with those three letters — which is
   * how `/api-dokumentation`, an ordinary marketing page at the time, got excluded from locale
   * routing and served a 404 while its neighbours worked. That page has since moved to its own
   * origin (`apps/docs`), but the slash stays: the next path beginning with "api" would hit the
   * same trap, and the exclusion is meant to name a route segment either way.
   */
  matcher: [
    "/((?!_next|_vercel|api/|favicon|opengraph-image|twitter-image|images|.*\\..*).*)",
  ],
};
