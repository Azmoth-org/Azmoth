import createMiddleware from "next-intl/middleware";

import { routing } from "./i18n/routing";

export default createMiddleware(routing);

export const config = {
  // Pages only — never static assets, API routes or files with an extension.
  matcher: ["/((?!_next|_vercel|api|favicon|og-image|images|.*\\..*).*)"],
};
