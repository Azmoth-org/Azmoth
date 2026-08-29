import createMiddleware from "next-intl/middleware";
import { NextResponse, type NextRequest } from "next/server";
import { routing } from "./i18n/routing";

const intlMiddleware = createMiddleware(routing);

export default function middleware(request: NextRequest) {
  // Arabic was removed from the site (Aug 2026) — permanently redirect all
  // /ar/* URLs to the French version of the same path so existing links and
  // search results keep working (Google follows 308s and transfers signals).
  const arMatch = request.nextUrl.pathname.match(/^\/ar(?:\/(.*))?$/);
  if (arMatch) {
    const rest = arMatch[1] ? `/${arMatch[1]}` : "";
    const target = new URL(`/fr${rest}${request.nextUrl.search}`, request.url);
    return NextResponse.redirect(target, 308);
  }

  const response = intlMiddleware(request);

  // next-intl redirects locale-less paths (/, /about, …) to the default
  // locale with a temporary 307. The mapping is permanent by design
  // (localePrefix: "always"), so upgrade it to 308 so search engines cache
  // the redirect instead of re-checking it on every crawl.
  if (response && response.status === 307) {
    const location = response.headers.get("location");
    if (location) {
      return NextResponse.redirect(location, 308);
    }
  }

  return response;
}

export const config = {
  // Skip all paths that aren't pages (static assets, APIs, etc.)
  matcher: ["/((?!_next|_vercel|api|favicon|og-image|fonts|logos|images|.*\\..*).*)"],
};
