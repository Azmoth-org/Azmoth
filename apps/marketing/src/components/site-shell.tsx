import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { getDocsUrl, getProductLinks } from "@/lib/site";

/**
 * The chrome around every marketing page.
 *
 * A server component, which is what lets it call `getProductLinks()` and `getDocsUrl()` —
 * those read `APP_URL` and `NEXT_PUBLIC_DOCS_URL` at request time, so a deployment can point
 * the "Anmelden" button or the documentation link somewhere else without rebuilding the image.
 * The header needs the three hrefs and is a client component (it owns the mobile sheet), so
 * they cross as props rather than as a `process.env` read that would be frozen into the bundle.
 */
export function SiteShell({ children }: { children: React.ReactNode }) {
  const productLinks = getProductLinks();
  const docsUrl = getDocsUrl();

  return (
    <div className="flex min-h-screen flex-col">
      <a
        href="#inhalt"
        className="sr-only focus:not-sr-only focus:absolute focus:top-4 focus:left-4 focus:z-100 focus:rounded-md focus:bg-primary focus:px-4 focus:py-2 focus:text-primary-foreground"
      >
        Zum Inhalt springen
      </a>
      <SiteHeader login={productLinks.login} demo={productLinks.demo} docs={docsUrl} />
      <main id="inhalt" className="flex-1">
        {children}
      </main>
      <SiteFooter />
    </div>
  );
}
