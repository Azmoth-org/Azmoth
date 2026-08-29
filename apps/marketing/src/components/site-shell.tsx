import { CookieBanner } from "@/components/cookie-banner";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";

/**
 * The chrome around every marketing page.
 *
 * A server component, unlike the shell it replaces: that one was `"use client"`
 * purely so it could read the pathname and decide whether to hide the navigation
 * on `/dashboard` and `/admin`. Those routes are gone — this site is public from
 * end to end — so nothing here needs the client.
 */
export function SiteShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col">
      <a
        href="#inhalt"
        className="sr-only focus:not-sr-only focus:absolute focus:top-4 focus:left-4 focus:z-100 focus:rounded-md focus:bg-primary focus:px-4 focus:py-2 focus:text-primary-foreground"
      >
        Zum Inhalt springen
      </a>
      <SiteHeader />
      <main id="inhalt" className="flex-1">
        {children}
      </main>
      <SiteFooter />
      <CookieBanner />
    </div>
  );
}
