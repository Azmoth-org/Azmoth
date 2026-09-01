"use client";

import type { ComponentProps, MouseEvent } from "react";

import { Link, useRouter, usePathname } from "@/i18n/navigation";
import { animatePageOut } from "@/lib/page-transition";

/**
 * An internal link that plays the curtain on the way out.
 *
 * It renders the locale-aware `Link` and intercepts the click, so it keeps everything a real
 * anchor gives you — a resolvable `href` in the status bar, middle-click, ⌘-click, "copy link
 * address", and the route prefetch next-intl's `Link` already does. Only the plain left-click is
 * taken over.
 *
 * ## What is deliberately not intercepted
 *
 * **Modified clicks.** ⌘/Ctrl/Shift/Alt-click and any non-primary button open a new tab or window.
 * Running a curtain over the *current* page for a navigation that is not happening in it is the
 * classic bug in hand-rolled transition links, and the upstream component this is ported from has
 * it: the sheet sweeps up and stays there while the visitor's new tab loads elsewhere.
 *
 * **Anchors, external hrefs and the current page.** In-page anchors are a scroll, not a
 * navigation; other origins are not this router's to push; and re-navigating to where you already
 * are should not stage a transition to nowhere.
 *
 * `prefers-reduced-motion` is not checked here — `animatePageOut` owns that decision and falls
 * back to an immediate `router.push`, so there is one place to change it rather than two that can
 * disagree.
 */
export function TransitionLink({
  href,
  onClick,
  ...props
}: ComponentProps<typeof Link>) {
  const router = useRouter();
  const pathname = usePathname();

  function handleClick(event: MouseEvent<HTMLAnchorElement>) {
    onClick?.(event);

    const target = typeof href === "string" ? href : (href.pathname ?? "/");

    if (
      event.defaultPrevented ||
      event.button !== 0 ||
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey ||
      target.startsWith("http") ||
      target.startsWith("#") ||
      target === pathname
    ) {
      return;
    }

    event.preventDefault();
    void animatePageOut(target, router);
  }

  return <Link href={href} onClick={handleClick} {...props} />;
}
