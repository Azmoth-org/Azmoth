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
   */
  matcher: [
    "/((?!_next|_vercel|api|favicon|opengraph-image|twitter-image|images|.*\\..*).*)",
  ],
};
