import { useTranslations } from "next-intl";

import { Separator } from "@workspace/ui/components/separator";

import { Logo } from "@/components/logo";
import { Link } from "@/i18n/navigation";
import { routes, siteConfig } from "@/lib/site";

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

  return (
    <footer className="border-t border-border/60">
      <div className="mx-auto max-w-6xl px-4 py-12 sm:px-6">
        <div className="grid gap-10 md:grid-cols-[2fr_1fr_1fr]">
          <div className="max-w-xs">
            <Logo />
            <p className="mt-3 text-sm text-muted-foreground">{t("claim")}</p>
          </div>

          {COLUMNS.map((column) => (
            <div key={column.key}>
              <h2 className="text-sm font-medium">{t(column.key)}</h2>
              <ul className="mt-3 flex flex-col gap-2">
                {column.links.map((link) => (
                  <li key={link.href}>
                    <Link
                      href={link.href}
                      className="text-sm text-muted-foreground transition-colors hover:text-foreground"
                    >
                      {tNav(link.key)}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <Separator className="my-8" />

        <div className="flex flex-col gap-2 text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
          <p>
            © {new Date().getFullYear()} {siteConfig.name}. {t("rechte")}
          </p>
          <p>{t("hinweis")}</p>
        </div>
      </div>
    </footer>
  );
}
