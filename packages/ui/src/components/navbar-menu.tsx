"use client";

import React from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";

import { cn } from "@workspace/ui/lib/utils";

/**
 * The dropdown half of the navigation — the panel that opens beneath a nav item.
 *
 * `resizable-navbar.tsx` owns the bar; this owns what hangs off it. See that file's header for why
 * the two are one component split in two, and for the seam (`NavItems`' `dropdown` prop) they meet
 * at. Nothing here observes scroll or knows the bar exists.
 *
 * ## Departures from the upstream component
 *
 * **The open/closed decision moved out.** Upstream's `MenuItem` renders its trigger *and* takes
 * `active`/`setActive`, so every consumer re-implements the same hover state and the same
 * `onMouseLeave` reset on the wrapping `<nav>`. Here the trigger and the state belong to
 * `NavItems`, and `NavDropdown` is handed a single `open` boolean. That is what lets one panel be
 * driven by hover *and* by keyboard focus without this file knowing about either.
 *
 * **A real exit animation.** Upstream renders `active !== null && (<motion.div initial animate>…)`
 * with no `AnimatePresence`, so the panel animates in and then vanishes on a frame boundary when
 * it closes. Half an animation is more noticeable than none.
 *
 * **`pointer-events-none` while closed.** The upstream panel is positioned `top: calc(100% +
 * 1.2rem)` with a `pt-4` spacer to bridge the gap the cursor crosses — a reasonable trick, but
 * combined with no exit animation it leaves an invisible 4rem-tall element over the page during
 * the frames it is fading. Anything under it stops being clickable.
 *
 * **Brand tokens and the shared glass.** `bg-white dark:bg-black` becomes the same `.azm-glass`
 * material the bar and the hero cards use, so the panel reads as part of the header rather than as
 * a white rectangle dropped onto it.
 */

/**
 * The panel's open and close curve.
 *
 * ## Why this is a tween and not a shared-layout `layoutId`
 *
 * The upstream component gives the panel `layoutId="active"`, so that moving between two nav items
 * slides one panel across rather than closing and reopening it. That is a nicer gesture, and it
 * does not survive being made per-item: each item owns its own `AnimatePresence`, and a `layoutId`
 * shared *across* two independent presence trees leaves the outgoing panel waiting on a
 * shared-layout handoff that its own tree cannot observe. It never resolves, so the element never
 * unmounts.
 *
 * The symptom is precise and was reproducible: every panel the visitor opened stayed in the DOM
 * for the rest of the session, stacked under the bar, so after touring the navigation there were
 * three invisible panels overlapping the page. Upstream does not hit it because it renders one
 * panel for the whole menu and keys it by which item is active — the same fix as hoisting the
 * presence out of the loop.
 *
 * Between two items the exit and the entrance overlap anyway, which at 180ms reads as the panel
 * moving rather than as two panels. That is most of the effect for none of the failure mode.
 */
const PANEL_TRANSITION = {
  duration: 0.18,
  ease: [0.16, 1, 0.3, 1],
} as const;

export function NavDropdown({
  open,
  children,
  className,
}: {
  open: boolean;
  children: React.ReactNode;
  className?: string;
}) {
  const reduceMotion = useReducedMotion();

  return (
    <AnimatePresence>
      {open ? (
        <motion.div
          initial={{ opacity: 0, y: 8, scale: 0.97 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 4, scale: 0.98 }}
          transition={reduceMotion ? { duration: 0 } : PANEL_TRANSITION}
          /*
            `pt-3` on the wrapper rather than a margin on the panel: it is the corridor the cursor
            travels from the trigger to the panel. As a margin the gap is dead space and the panel
            closes halfway down.
          */
          className="absolute top-full left-1/2 z-50 -translate-x-1/2 pt-3"
        >
          {/*
            A heavier tint than the bar's, through the `--azm-glass-tint` override the class
            exposes. The bar overlays a 4rem strip; this panel hangs down over the hero headline at
            56px, and 13px menu copy competing with display type showing through it is the
            difference between "glass" and "unreadable".
          */}
          <div
            className={cn(
              "azm-glass overflow-hidden rounded-2xl [--azm-glass-tint:oklch(1_0_0/0.93)]",
              className
            )}
          >
            <div className="w-max max-w-sm p-3">{children}</div>
          </div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}

/**
 * A simple row in a dropdown — the muted-to-ink hover is the same one the bar's own links use, so
 * a visitor's eye does not have to relearn what "interactive" looks like two levels into the same
 * control.
 *
 * Exported as a class string rather than only as a component, because half the rows in a real
 * navigation are not `<a>` elements: an internal route needs the app's own router link, which
 * cannot be produced by a component in a UI package that knows nothing about routing. A shared
 * class is the honest seam — the component below is the convenience wrapper for the outbound case.
 */
export const navDropdownLinkClass =
  "block rounded-lg px-3 py-2 text-sm text-azm-ink-secondary transition-colors hover:bg-azm-ink/5 hover:text-azm-ink";

export function NavDropdownLink({ className, ...props }: React.ComponentProps<"a">) {
  return <a className={cn(navDropdownLinkClass, className)} {...props} />;
}

/**
 * A titled entry with a line of supporting copy — the richer of the two dropdown rows.
 *
 * Upstream's equivalent (`ProductItem`) pairs the text with a 140x70 `<img>`. There is nothing to
 * put in it here: this product's dropdown lists capabilities, not products with screenshots, and a
 * thumbnail per row would be four requests on the critical path to decorate four links. The
 * optional `icon` slot carries the same weight at a fraction of the cost.
 *
 * `render` takes the anchor rather than this component hard-coding one, because internal rows need
 * the locale-aware router link and outbound rows need a plain `<a>` — the same split the bar makes.
 */
export function NavDropdownItem({
  title,
  description,
  icon,
  render,
}: {
  title: string;
  description: string;
  icon?: React.ReactNode;
  render: (children: React.ReactNode, className: string) => React.ReactNode;
}) {
  return render(
    <>
      {icon ? (
        <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
          {icon}
        </span>
      ) : null}
      <span className="flex flex-col gap-0.5">
        <span className="text-sm font-medium text-azm-ink">{title}</span>
        <span className="text-xs leading-relaxed text-azm-ink-mute">{description}</span>
      </span>
    </>,
    "flex items-start gap-3 rounded-lg p-3 transition-colors hover:bg-azm-ink/5"
  );
}
