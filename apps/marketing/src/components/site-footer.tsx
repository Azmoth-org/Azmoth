import { useTranslations } from "next-intl";

import { Separator } from "@workspace/ui/components/separator";
import { Logo } from "@workspace/ui/components/logo";

import { TransitionLink } from "@/components/transition-link";
import { apiDocsUrl, getDocsUrl, routes, siteConfig } from "@/lib/site";

/**
 * Four columns, and the fourth is the one German law cares about.
 *
 * Impressum and Datenschutz have to be reachable from every page in at most two clicks —
 * "leicht erkennbar, unmittelbar erreichbar und ständig verfügbar" under § 5 DDG — and a
 * site-wide footer is the ordinary way to satisfy that. They are their own column rather
 * than an afterthought in the fine-print row for the same reason: a link nobody can find
 * is not "unmittelbar erreichbar".
 */
const COLUMNS = [
  {
    key: "produkt",
    links: [
      { href: routes.funktionen, key: "funktionen" },
      { href: routes.faq, key: "faq" },
    ],
  },
  {
    key: "unternehmen",
    links: [
      { href: routes.ueberUns, key: "ueberUns" },
      { href: routes.kontakt, key: "kontakt" },
    ],
  },
] as const;

export function SiteFooter() {
  const t = useTranslations("footer");
  const tNav = useTranslations("navigation");
  /*
   * A server component, so this is a direct read rather than a prop. The documentation lives on
   * its own origin — see `getDocsUrl()` — which is why it sits beside the API reference in the
   * outbound column rather than in the internal "Produkt" list above.
   */
  const docsUrl = getDocsUrl();

  const linkClass =
    "text-sm text-muted-foreground transition-colors hover:text-foreground";

  return (
    <footer className="border-t border-azm-hairline bg-white">
      <div className="mx-auto max-w-6xl px-4 py-14 sm:px-6">
        <div className="grid gap-10 md:grid-cols-2 lg:grid-cols-[2fr_1fr_1fr_1.2fr]">
          <div className="max-w-xs">
            <Logo />
            <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
              {t("claim")}
            </p>
          </div>

          {COLUMNS.map((column) => (
            <div key={column.key}>
              <h2 className="text-sm font-medium">{t(column.key)}</h2>
              <ul className="mt-3 flex flex-col gap-2">
                {column.links.map((link) => (
                  <li key={link.href}>
                    <TransitionLink href={link.href} className={linkClass}>
                      {tNav(link.key)}
                    </TransitionLink>
                  </li>
                ))}
              </ul>
            </div>
          ))}

          <div>
            <h2 className="text-sm font-medium">{t("rechtliches")}</h2>
            <ul className="mt-3 flex flex-col gap-2">
              <li>
                <TransitionLink href={routes.impressum} className={linkClass}>
                  {t("impressum")}
                </TransitionLink>
              </li>
              <li>
                <TransitionLink href={routes.datenschutz} className={linkClass}>
                  {t("datenschutz")}
                </TransitionLink>
              </li>
              {/*
                This row used to be a GitHub link. The repository is private, so it led
                every visitor to a sign-in wall; the interactive API reference is the
                thing an integrator actually wanted and is served to anyone.
              */}
              <li>
                <a href={docsUrl} className={linkClass}>
                  {tNav("dokumentation")}
                </a>
              </li>
              <li>
                <a
                  href={apiDocsUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className={linkClass}
                >
                  {t("apiReferenz")}
                </a>
              </li>
              <li>
                <a href={`mailto:${siteConfig.email}`} className={linkClass}>
                  {siteConfig.email}
                </a>
              </li>
            </ul>
          </div>
        </div>

        <Separator className="my-8" />

        <div className="flex flex-col gap-3 text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
          {/*
            `getFullYear()` at render time. Every page here is statically prerendered, so
            in practice this is the build year rather than the visitor's — which is the
            correct behaviour for a copyright line and, unlike a hard-coded literal, is
            not wrong the following January.
          */}
          <p className="azm-tnum">
            © {new Date().getFullYear()} {siteConfig.name}. {t("rechte")}
          </p>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-4">
            <p>{t("hinweis")}</p>
            <p className="flex items-center gap-1.5 font-medium text-azm-ink-secondary">
              <span aria-hidden="true">🇩🇪</span>
              {t("madeInGermany")}
            </p>
          </div>
        </div>
      </div>
    </footer>
  );
}
