import { PageTransitionOverlay } from "@/components/page-transition-overlay";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { SmoothScroll } from "@/components/smooth-scroll";
import { getDocsUrl, getProductLinks } from "@/lib/site";

/**
 * The chrome around every marketing page.
 *
 * A server component, which is what lets it call `getProductLinks()` and `getDocsUrl()` — those
 * read `APP_URL` and `NEXT_PUBLIC_DOCS_URL`, and the header is a client component, so they cross
 * as props rather than as a `process.env` read that would be frozen into the browser bundle.
 *
 * Two things were added when the site was rebuilt, and both belong *here* rather than in a page
 * for the same reason: they must not remount on navigation. The curtain overlay is mid-animation
 * during a route change — remounting it is the animation disappearing — and Lenis owns the
 * document's scroll, so a fresh instance per page means the scroll position resets and the
 * inertial state is thrown away between every click.
 */
export function SiteShell({ children }: { children: React.ReactNode }) {
  const productLinks = getProductLinks();
  const docsUrl = getDocsUrl();

  return (
    <div className="flex min-h-screen flex-col">
      <a
        href="#inhalt"
        className="sr-only focus:not-sr-only focus:absolute focus:top-4 focus:left-4 focus:z-100 focus:rounded-full focus:bg-primary focus:px-4 focus:py-2 focus:text-primary-foreground"
      >
        Zum Inhalt springen
      </a>

      <SiteHeader
        login={productLinks.login}
        demo={productLinks.demo}
        docs={docsUrl}
      />

      {/*
        `pt-16` for the header, which is `fixed` rather than `sticky` since the rebuild — see
        `resizable-navbar.tsx` for why. A fixed element is out of flow, so without this the hero's
        first 4rem sit underneath it. Padding on the wrapper rather than a spacer div: a spacer is
        an element a future section can accidentally `-mt` its way past, and this cannot be.
      */}
      <main id="inhalt" className="flex-1 pt-16">
        {children}
      </main>

      <SiteFooter />

      <PageTransitionOverlay />
      <SmoothScroll />
    </div>
  );
}
