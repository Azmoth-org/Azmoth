"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { MenuIcon } from "lucide-react";

import { Button } from "@workspace/ui/components/button";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@workspace/ui/components/sheet";

import { Logo } from "@/components/logo";
import { Link } from "@/i18n/navigation";
import { routes, siteConfig } from "@/lib/site";

const NAV_ITEMS = [
  { href: routes.funktionen, key: "funktionen" },
  { href: routes.faq, key: "faq" },
  { href: routes.ueberUns, key: "ueberUns" },
  { href: routes.kontakt, key: "kontakt" },
] as const;

export function SiteHeader() {
  const t = useTranslations("navigation");
  const [open, setOpen] = useState(false);

  return (
    <header className="sticky top-0 z-50 border-b border-border/60 bg-background/80 backdrop-blur-md">
      <nav
        aria-label={t("ariaLabel")}
        className="mx-auto flex h-16 max-w-6xl items-center gap-6 px-4 sm:px-6"
      >
        <Link href={routes.home} className="shrink-0" aria-label={siteConfig.name}>
          <Logo />
        </Link>

        <ul className="hidden flex-1 items-center gap-1 md:flex">
          {NAV_ITEMS.map((item) => (
            <li key={item.href}>
              <Link
                href={item.href}
                className="rounded-md px-3 py-2 text-sm text-muted-foreground transition-colors hover:text-foreground"
              >
                {t(item.key)}
              </Link>
            </li>
          ))}
        </ul>

        <div className="ml-auto hidden items-center gap-2 md:flex">
          {/*
           * Plain <a>, not the i18n <Link>: the product is a separate Next application
           * on another origin, so a client-side transition would 404 inside this one.
           */}
          <Button variant="ghost" size="sm" render={<a href={siteConfig.login} />}>
            {t("anmelden")}
          </Button>
          <Button size="sm" render={<a href={siteConfig.signup} />}>
            {t("testen")}
          </Button>
        </div>

        <Sheet open={open} onOpenChange={setOpen}>
          <SheetTrigger
            render={
              <Button
                variant="ghost"
                size="icon"
                className="ml-auto md:hidden"
                aria-label={t("menueOeffnen")}
              >
                <MenuIcon />
              </Button>
            }
          />
          <SheetContent side="right" className="w-72">
            <SheetHeader>
              <SheetTitle>{t("menue")}</SheetTitle>
            </SheetHeader>
            <div className="flex flex-col gap-1 px-4">
              {NAV_ITEMS.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  onClick={() => setOpen(false)}
                  className="rounded-md px-3 py-2.5 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                >
                  {t(item.key)}
                </Link>
              ))}
            </div>
            <div className="mt-4 flex flex-col gap-2 px-4">
              <Button variant="outline" render={<a href={siteConfig.login} />}>
                {t("anmelden")}
              </Button>
              <Button render={<a href={siteConfig.signup} />}>{t("testen")}</Button>
            </div>
          </SheetContent>
        </Sheet>
      </nav>
    </header>
  );
}
