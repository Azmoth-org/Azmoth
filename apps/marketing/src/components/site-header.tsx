"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { BookOpenIcon, LayersIcon, ScaleIcon, TerminalIcon } from "lucide-react";

import { Logo } from "@workspace/ui/components/logo";
import {
  MobileNav,
  MobileNavHeader,
  MobileNavMenu,
  MobileNavToggle,
  NavBody,
  NavDropdownItem,
  NavItems,
  Navbar,
  navDropdownLinkClass,
  type NavItem,
} from "@workspace/ui/components/resizable-navbar";

import { ButtonLink } from "@/components/button-link";
import { TransitionLink } from "@/components/transition-link";
import { Link } from "@/i18n/navigation";
import { routes, siteConfig } from "@/lib/site";

/**
 * The site navigation: the resizable glass bar, with dropdowns hanging off two of its four items.
 *
 * The shell and the dropdown are `@workspace/ui`'s — see `resizable-navbar.tsx` for why those are
 * one component split in two. What lives here is the only part that is genuinely this site's: the
 * information architecture, the German labels, and which of the three origins each link points at.
 *
 * ## Why four top-level items and not seven
 *
 * The site has seven routes plus two outbound origins. Listing all of them flat is the version
 * this replaces, and it forced two compromises: the documentation link sat between "Über uns" and
 * "Kontakt" with nothing to say it left the site, and there was nowhere to put the API reference
 * at all — it existed only in the footer. Grouping into four gives every destination a place and
 * gives the outbound ones a line of copy explaining that they are outbound.
 *
 * ## Three kinds of link, and they are not interchangeable
 *
 * - **`TransitionLink`** for internal routes. Plays the curtain, then pushes.
 * - **`Link`** for in-page anchors. The curtain would be wrong for a scroll, and `TransitionLink`
 *   declines them for that reason — but they still need the locale-aware href.
 * - **Plain `<a>`** for the product app, the documentation site and the API reference. Three
 *   separate origins; a client-side push would resolve against this host and 404.
 *
 * This is a client component, so the three hrefs that come from the environment arrive as props
 * from `SiteShell` rather than being read here — a `process.env` read in this file would be frozen
 * into the browser bundle at build time.
 */
export function SiteHeader({
  login,
  demo,
  docs,
  apiDocs,
}: {
  login: string;
  demo: string;
  /** `docs.azmoth.com` — the orientation material, its own Next application. */
  docs: string;
  /** `api.azmoth.com/docs` — the interactive schema the running engine serves. */
  apiDocs: string;
}) {
  const t = useTranslations("navigation");
  const [open, setOpen] = useState(false);

  const close = () => setOpen(false);

  /*
   * The mobile list is flat and complete where the desktop one is grouped. A phone has no hover,
   * so a dropdown becomes a second tap on the way to every destination; a single scrollable column
   * is both fewer taps and the pattern every other mobile site uses.
   */
  const mobileLinks = [
    { href: routes.funktionen, label: t("funktionen") },
    { href: "/#loesung", label: t("ablauf") },
    { href: routes.faq, label: t("faq") },
    { href: routes.ueberUns, label: t("ueberUns") },
    { href: routes.kontakt, label: t("kontakt") },
  ] as const;

  const items: NavItem[] = [
    {
      name: t("funktionen"),
      link: routes.funktionen,
      render: ({ className, children }) => (
        <TransitionLink href={routes.funktionen} className={className}>
          {children}
        </TransitionLink>
      ),
      dropdown: (
        <div className="flex w-72 flex-col">
          <NavDropdownItem
            title={t("funktionen")}
            description={t("beschreibung.funktionen")}
            icon={<LayersIcon className="size-4" aria-hidden="true" />}
            render={(children, className) => (
              <TransitionLink href={routes.funktionen} className={className}>
                {children}
              </TransitionLink>
            )}
          />
          <NavDropdownItem
            title={t("buckets")}
            description={t("beschreibung.buckets")}
            icon={<ScaleIcon className="size-4" aria-hidden="true" />}
            render={(children, className) => (
              <Link href="/#kategorien" className={className}>
                {children}
              </Link>
            )}
          />
        </div>
      ),
    },
    {
      name: t("ablauf"),
      link: "/#loesung",
      /*
        The locale-aware `Link`, not `TransitionLink`. This is an in-page anchor: the curtain would
        sweep the screen for a scroll, and from any other page it is a navigation *and* a scroll,
        which `TransitionLink` deliberately declines to stage. Lenis handles the smooth part.
      */
      render: ({ className, children }) => (
        <Link href="/#loesung" className={className}>
          {children}
        </Link>
      ),
    },
    {
      name: t("entwickler"),
      link: docs,
      /* No `render`: the default plain `<a href>` is exactly right for another origin. */
      dropdown: (
        <div className="flex w-72 flex-col">
          <NavDropdownItem
            title={t("dokumentation")}
            description={t("beschreibung.dokumentation")}
            icon={<BookOpenIcon className="size-4" aria-hidden="true" />}
            render={(children, className) => (
              <a href={docs} className={className}>
                {children}
              </a>
            )}
          />
          <NavDropdownItem
            title={t("apiReferenz")}
            description={t("beschreibung.apiReferenz")}
            icon={<TerminalIcon className="size-4" aria-hidden="true" />}
            render={(children, className) => (
              // `noreferrer` alongside `noopener`: another origin has no need for this one's referrer.
              <a
                href={apiDocs}
                target="_blank"
                rel="noopener noreferrer"
                className={className}
              >
                {children}
              </a>
            )}
          />
        </div>
      ),
    },
    {
      name: t("unternehmen"),
      link: routes.ueberUns,
      render: ({ className, children }) => (
        <TransitionLink href={routes.ueberUns} className={className}>
          {children}
        </TransitionLink>
      ),
      dropdown: (
        <div className="flex w-64 flex-col">
          {[
            { href: routes.ueberUns, label: t("ueberUns") },
            { href: routes.faq, label: t("faq") },
            { href: routes.kontakt, label: t("kontakt") },
          ].map((entry) => (
            // The shared class rather than `NavDropdownLink`: these are internal routes, so they
            // need this app's router link. See `navDropdownLinkClass` for why that seam exists.
            <TransitionLink
              key={entry.href}
              href={entry.href}
              className={navDropdownLinkClass}
            >
              {entry.label}
            </TransitionLink>
          ))}
        </div>
      ),
    },
  ];

  return (
    <Navbar>
      <NavBody>
        <TransitionLink
          href={routes.home}
          className="relative z-10 shrink-0"
          aria-label={siteConfig.name}
        >
          <Logo />
        </TransitionLink>

        <NavItems items={items} />

        <div className="relative z-10 flex shrink-0 items-center gap-2">
          <ButtonLink external href={login} variant="ghost" size="sm">
            {t("anmelden")}
          </ButtonLink>
          <ButtonLink external href={demo} size="sm">
            {t("testen")}
          </ButtonLink>
        </div>
      </NavBody>

      <MobileNav>
        <MobileNavHeader>
          <TransitionLink href={routes.home} aria-label={siteConfig.name} onClick={close}>
            <Logo />
          </TransitionLink>
          <MobileNavToggle
            isOpen={open}
            onClick={() => setOpen((value) => !value)}
            label={open ? t("menueSchliessen") : t("menueOeffnen")}
          />
        </MobileNavHeader>

        <MobileNavMenu isOpen={open}>
          <nav aria-label={t("ariaLabel")} className="flex flex-col">
            {mobileLinks.map((entry) => (
              <TransitionLink
                key={entry.href}
                href={entry.href}
                onClick={close}
                className="rounded-lg px-3 py-2.5 text-sm text-azm-ink-secondary transition-colors hover:bg-azm-ink/5 hover:text-azm-ink"
              >
                {entry.label}
              </TransitionLink>
            ))}
            <a
              href={docs}
              onClick={close}
              className="rounded-lg px-3 py-2.5 text-sm text-azm-ink-secondary transition-colors hover:bg-azm-ink/5 hover:text-azm-ink"
            >
              {t("dokumentation")}
            </a>
          </nav>
          <div className="mt-3 flex flex-col gap-2 border-t border-azm-hairline pt-3">
            <ButtonLink external href={login} variant="outline">
              {t("anmelden")}
            </ButtonLink>
            <ButtonLink external href={demo}>
              {t("testen")}
            </ButtonLink>
          </div>
        </MobileNavMenu>
      </MobileNav>
    </Navbar>
  );
}
