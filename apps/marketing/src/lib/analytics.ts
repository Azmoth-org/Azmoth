/**
 * Reach measurement, off by default and cookieless when it is on.
 *
 * This used to load Google Analytics 4 behind a consent banner. That is defensible in
 * general and a poor fit here specifically: the audience is German billing centres and
 * PVS vendors, the home page argues for the product on DSGVO grounds, and several German
 * supervisory authorities have found GA use unlawful over the US transfer question. A
 * site making a data-protection argument should not open by asking permission to send
 * its visitors to Google.
 *
 * So the provider is Plausible or Umami. Both are cookieless and store no identifier on
 * the device, which changes what the page has to do rather than only who receives the
 * data: § 25 TDDDG governs *storing or reading* information on a terminal device, and
 * neither of these does. That is why there is no consent banner any more.
 *
 * **None of this runs unless it is configured.** With `NEXT_PUBLIC_ANALYTICS_PROVIDER`
 * unset — which is the default, and the state the site launches in — `getAnalytics()`
 * returns `null`, no script tag is emitted and nothing is measured. Maximum privacy is
 * not a setting somebody has to remember to choose; it is what happens when nobody
 * chooses anything.
 */

type Provider = "plausible" | "umami";

export type AnalyticsConfig = {
  provider: Provider;
  /** The script URL, self-hosted or the vendor's cloud. */
  src: string;
  /** Plausible: the site domain. Umami: the website id. */
  siteId: string;
};

/**
 * The configured provider, or `null` when there is none.
 *
 * Read through `NEXT_PUBLIC_` variables because the script tag is emitted in the browser
 * bundle, and inlined at build time like every other value on this statically prerendered
 * site — changing it means a rebuild, which is the same trade `APP_URL` makes.
 */
export function getAnalytics(): AnalyticsConfig | null {
  const provider = process.env.NEXT_PUBLIC_ANALYTICS_PROVIDER;
  const src = process.env.NEXT_PUBLIC_ANALYTICS_SRC;
  const siteId = process.env.NEXT_PUBLIC_ANALYTICS_SITE_ID;

  if (provider !== "plausible" && provider !== "umami") return null;
  if (!src || !siteId) return null;

  return { provider, src, siteId };
}
