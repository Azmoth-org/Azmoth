import { ArrowUpRightIcon } from "lucide-react";
import type { BaseLayoutProps } from "fumadocs-ui/layouts/shared";

import { Logo } from "@workspace/ui/components/logo";

import { getAppUrl, getSiteUrl } from "@/lib/site";

/**
 * The chrome Fumadocs draws around every page: the navbar title and the links beside it.
 *
 * It sits in its own module rather than inline in `app/(docs)/layout.tsx` because Fumadocs'
 * other layouts (the 404 shell, and a marketing-style `HomeLayout` if this site ever grows one)
 * take the same object. One export means those cannot drift into two different navbars.
 *
 * A function rather than a constant: `getSiteUrl()` and `getAppUrl()` read the environment, and
 * a module-level constant would freeze whatever was set when the module first evaluated.
 */
export function baseOptions(): BaseLayoutProps {
  return {
    nav: {
      /*
       * The real lockup from `@workspace/ui`, not Fumadocs' text title.
       *
       * The monogram is a `mask-image` over `currentColor`, so it inherits the navbar's ink in
       * both themes — which is the reason the component was worth sharing rather than
       * re-drawing here. `public/brand/azmoth-mark.png` must exist on this origin for it;
       * `scripts/build-brand-assets.mjs` writes it.
       */
      title: <Logo className="text-fd-foreground" label="Azmoth-Dokumentation" />,
      url: "/",
      transparentMode: "none",
    },
    /*
     * No theme switch. The site is light-only — `app/layout.tsx` says why — and Fumadocs would
     * otherwise render a control that writes a `dark` class no stylesheet answers to, which is
     * worse than not offering it: a button that visibly does nothing.
     */
    themeSwitch: { enabled: false },
    links: [
      {
        type: "main",
        text: "Zur Website",
        url: getSiteUrl(),
        external: true,
      },
      {
        type: "button",
        text: "Anmelden",
        url: `${getAppUrl()}/login`,
        external: true,
        icon: <ArrowUpRightIcon />,
      },
    ],
  };
}
