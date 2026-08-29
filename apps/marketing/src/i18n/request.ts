import { hasLocale } from "next-intl";
import { getRequestConfig } from "next-intl/server";

import { routing } from "./routing";

export default getRequestConfig(async ({ requestLocale }) => {
  const requested = await requestLocale;
  const locale = hasLocale(routing.locales, requested)
    ? requested
    : routing.defaultLocale;

  return {
    locale,
    // Pinned, not inferred. Without it next-intl uses the server's zone, so a date
    // formatted at build time depends on where the build ran.
    timeZone: "Europe/Berlin",
    messages: (await import(`../../messages/${locale}.json`)).default,
  };
});
