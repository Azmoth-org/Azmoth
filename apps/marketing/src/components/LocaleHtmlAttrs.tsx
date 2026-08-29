"use client";

import { useEffect } from "react";

/**
 * Keeps <html dir/lang> in sync with the active locale — including on
 * client-side navigation via the language switcher (the pre-paint script
 * in the layout only runs on full page loads).
 */
export default function LocaleHtmlAttrs({
  locale,
  isRtl,
}: {
  locale: string;
  isRtl: boolean;
}) {
  useEffect(() => {
    document.documentElement.setAttribute("dir", isRtl ? "rtl" : "ltr");
    document.documentElement.setAttribute("lang", locale);
  }, [locale, isRtl]);

  return null;
}
