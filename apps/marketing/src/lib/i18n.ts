import en from "../../messages/en.json";
import fr from "../../messages/fr.json";

export const locales = ["en", "fr"] as const;
export type Locale = (typeof locales)[number];

export const defaultLocale: Locale = "en";

const dictionaries: Record<Locale, Record<string, unknown>> = {
  en: en as Record<string, unknown>,
  fr: fr as Record<string, unknown>,
};

export function getDictionary(locale: string): Record<string, unknown> {
  const l = locale as Locale;
  return dictionaries[l] || dictionaries.en;
}

export function getNestedValue(
  obj: unknown,
  path: string
): unknown {
  return path.split(".").reduce((acc: unknown, part: string) => {
    if (acc && typeof acc === "object" && part in (acc as Record<string, unknown>)) {
      return (acc as Record<string, unknown>)[part];
    }
    return undefined;
  }, obj);
}

export function detectLocale(acceptLanguage: string): Locale {
  if (!acceptLanguage) return defaultLocale;
  const preferred = acceptLanguage.split(",")[0]?.split("-")[0]?.trim().toLowerCase();
  if (locales.includes(preferred as Locale)) {
    return preferred as Locale;
  }
  return defaultLocale;
}
