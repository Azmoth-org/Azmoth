import { defineRouting } from "next-intl/routing";

/**
 * German only, for now.
 *
 * Azmoth bills against the GOÄ — a German fee schedule — so there is no second
 * audience to serve yet and no honest way to translate "Analogansatz" for one.
 * next-intl stays in place regardless: the copy is already in a message catalogue
 * rather than in JSX, so adding a locale later is this array plus a JSON file, not
 * a pass over every page.
 *
 * `as-needed` keeps the default locale unprefixed, so the public URLs are `/preise`
 * rather than `/de/preise`.
 */
export const routing = defineRouting({
  locales: ["de"],
  defaultLocale: "de",
  localePrefix: "as-needed",
});

export type Locale = (typeof routing.locales)[number];
