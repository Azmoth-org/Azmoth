"use client";

import React, { useEffect, useRef, useState } from "react";
import {
  AnimatePresence,
  motion,
  useMotionValueEvent,
  useReducedMotion,
  useScroll,
} from "motion/react";
import { MenuIcon, XIcon } from "lucide-react";

import { cn } from "@workspace/ui/lib/utils";
import { NavDropdown } from "@workspace/ui/components/navbar-menu";

/**
 * The navigation shell: a full-width bar that contracts into a floating glass pill on scroll.
 *
 * ## What this is, and what `navbar-menu.tsx` is
 *
 * These two files are one component split along the axis they actually differ on. This one owns
 * the **shell** — where the bar sits, how wide it is, what it is made of, and how it collapses on
 * a phone. Its sibling owns the **dropdown** — the panel that opens under a nav item and the
 * shared-layout animation that slides it between items. They were separate upstream components
 * (Aceternity's "Resizable Navbar" and "Navbar Menu") and each was missing the other's half: the
 * resizable one had no way to hold a submenu, and the menu one was a static centred pill with no
 * scroll behaviour and no mobile story.
 *
 * The seam between them is `NavItems`, which takes an optional `dropdown` per item and renders it
 * through the sibling's `NavDropdown`. Nothing else crosses.
 *
 * ## Departures from the upstream component
 *
 * **`fixed`, not `sticky top-20`.** Upstream parks the bar 5rem down the page and lets it stick
 * there, which means the first 80px of every page scrolls with no navigation on it at all. A
 * marketing site's header is the primary way out of a page; it does not get to be absent above the
 * fold.
 *
 * **`useScroll()` on the window rather than on `ref`.** Upstream passes `target: ref` with a
 * `["start start", "end start"]` offset while the element is `position: sticky` — a sticky element
 * never leaves its scrollport by that measure, so the progress it computes is not what it looks
 * like it computes. The threshold wanted here is simply "has the visitor scrolled past the hero's
 * first screenful", which is `scrollY` and nothing else.
 *
 * **A hysteresis band instead of one threshold.** A single `latest > 100` flips state on every
 * frame while the visitor idles at exactly 100px — a trackpad's inertial tail sits there for a
 * second — and the bar visibly flutters between its two widths. Contracting at 80 and expanding
 * again only below 20 costs one constant and removes the failure mode.
 *
 * **`minWidth: 800px` is gone.** It was an inline style on the desktop body, and it is the reason
 * the upstream navbar overflows a 1024px tablet in landscape: 800px of nav plus the page's own
 * gutters exceeds the viewport and the document scrolls sideways. Width is expressed in
 * `max-w-*` and clamped by the parent instead, which is what CLS-free responsive behaviour needs.
 *
 * **Brand tokens, not `bg-white/80` and `text-neutral-600`.** Every colour here resolves through
 * `DESIGN.md`, so the header cannot drift from the surface below it.
 */

/** Scroll offset (px) at which the bar contracts into its floating state. */
const CONTRACT_AT = 80;

/**
 * ...and the offset it must fall back below to expand again. The gap between the two is the
 * hysteresis band; without it the bar oscillates whenever the visitor rests on the threshold.
 */
const EXPAND_AT = 20;

/**
 * The spring the bar resizes on.
 *
 * Heavily damped and deliberately not bouncy. A navigation bar that overshoots its width reads as
 * a glitch rather than as a flourish — this is chrome, and chrome should move like it has mass.
 */
const RESIZE_SPRING = {
  type: "spring",
  stiffness: 220,
  damping: 40,
  mass: 0.7,
} as const;

export type NavItem = {
  name: string;
  link: string;
  /**
   * The anchor to render for this item.
   *
   * It is a render prop and not a `href` string, because a navigation on a real site has two
   * incompatible kinds of link in the same row: internal routes need the app's own router
   * component — locale-aware, prefetching, and on this site playing the page-transition curtain —
   * while the documentation and API origins need a plain `<a>`, since a client-side push would
   * resolve against the wrong host. A UI package cannot produce the first of those; it does not
   * know what router the consumer has.
   *
   * Omitting it yields a plain `<a href={link}>`, which is the right default for an outbound item.
   *
   * The previous version of this file rendered a bare `<span>` for anything not marked `external`,
   * on the assumption the call site would supply the anchor somehow. It never could: the result
   * was three top-level navigation entries that could not be clicked, could not be focused, and
   * did not appear in the tab order at all.
   */
  render?: (props: { className: string; children: React.ReactNode }) => React.ReactNode;
  /**
   * A panel to open beneath this item on hover or focus. Supplied by the call site — this file
   * knows nothing about what goes in it beyond that it is React.
   */
  dropdown?: React.ReactNode;
};

/** The link chrome, shared by the default anchor and by whatever a call site renders instead. */
const NAV_LINK_CLASS =
  /*
    `whitespace-nowrap` is load-bearing, not cosmetic. The bar contracts on scroll and the link row
    is the part that gives, so a three-word label ("So funktioniert es") wraps inside a 64px-tall
    pill and pushes the bar's height with it. A navigation label never wants to wrap; the bar's
    `max-w` is what absorbs the pressure instead.
  */
  "relative block rounded-full px-4 py-2 text-sm whitespace-nowrap text-azm-ink-secondary transition-colors hover:text-azm-ink";

/**
 * The scroll observer and the state owner. Children receive `visible` by cloning, which is how the
 * desktop body and the mobile bar stay in step without the call site threading a boolean through
 * both.
 */
export function Navbar({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  const { scrollY } = useScroll();
  const [visible, setVisible] = useState(false);

  useMotionValueEvent(scrollY, "change", (latest) => {
    setVisible((current) => {
      if (!current && latest > CONTRACT_AT) return true;
      if (current && latest < EXPAND_AT) return false;
      return current;
    });
  });

  return (
    <header className={cn("fixed inset-x-0 top-0 z-50 w-full", className)}>
      {React.Children.map(children, (child) =>
        React.isValidElement(child)
          ? React.cloneElement(child as React.ReactElement<{ visible?: boolean }>, {
              visible,
            })
          : child
      )}
    </header>
  );
}

/**
 * The desktop bar.
 *
 * Two things animate and neither is `width` in the layout sense: `maxWidth` and the border radius.
 * Animating `width` on a flex parent re-runs layout for the whole subtree every frame; animating
 * `maxWidth` on an element that is already `w-full` reaches the same visual result while the
 * children keep their own intrinsic sizing.
 *
 * The glass itself is a sibling `<div>` behind the content rather than a background on this
 * element. A `backdrop-filter` establishes a containing block for fixed-position descendants,
 * which is exactly the bug that makes a dropdown panel inside a blurred bar clip at the bar's
 * bounds instead of overhanging the page.
 */
export function NavBody({
  children,
  className,
  visible,
}: {
  children: React.ReactNode;
  className?: string;
  visible?: boolean;
}) {
  const reduceMotion = useReducedMotion();

  return (
    <motion.div
      animate={{
        /*
          64rem contracted against 72rem expanded. The gap is deliberately modest: the upstream
          component collapses to 40 % of the page width, which looks striking in a demo holding
          four one-word links and clips the moment a real navigation has a logo, four German
          labels and two buttons in it. The visible change here is the pill forming and lifting,
          not the width — which is the part that reads as expensive anyway.
        */
        maxWidth: visible ? "64rem" : "72rem",
        y: visible ? 12 : 0,
      }}
      initial={false}
      transition={reduceMotion ? { duration: 0 } : RESIZE_SPRING}
      className={cn(
        "relative z-10 mx-auto hidden w-full items-center gap-6 px-4 lg:flex",
        className
      )}
    >
      <motion.div
        aria-hidden="true"
        initial={false}
        animate={{ opacity: visible ? 1 : 0 }}
        transition={{ duration: reduceMotion ? 0 : 0.25, ease: [0.16, 1, 0.3, 1] }}
        className="azm-glass pointer-events-none absolute inset-0 -z-10 rounded-full"
      />
      <div className="flex h-16 w-full items-center gap-6">{children}</div>
    </motion.div>
  );
}

/**
 * The centre link group.
 *
 * The hover pill is a single element moved between items by `layoutId`, not one element per item
 * cross-fading — which is what makes it slide rather than blink. `layoutId` is namespaced with a
 * literal that appears nowhere else in the tree: a bare `"hovered"` (the upstream value) collides
 * with any other shared-layout element on the page, and the symptom is a pill that flies across
 * the viewport to a card on scroll.
 *
 * Hover *and* focus open a dropdown. Upstream binds `onMouseEnter` only, which leaves the submenu
 * unreachable by keyboard — on a site whose own copy argues for accessibility of evidence, a
 * navigation branch a screen-reader user cannot open is not a detail.
 */
export function NavItems({
  items,
  className,
  onItemClick,
}: {
  items: readonly NavItem[];
  className?: string;
  onItemClick?: () => void;
}) {
  const [hovered, setHovered] = useState<number | null>(null);
  const [openMenu, setOpenMenu] = useState<string | null>(null);

  /**
   * A pending "focus left the group" close, so an arriving open can cancel it.
   *
   * Closing on focus-out has to be deferred — at the moment `focusout` fires, focus has left the
   * old element and not yet reached the new one, so there is nothing truthful to test. Deferring
   * it introduces the opposite problem: when the visitor tabs from one dropdown trigger straight
   * to the next, the deferred close lands *after* the new item's open and silently undoes it.
   *
   * The symptom was precise and looked like nonsense — the menu opened on every *other* trigger.
   * Tab to "Funktionen" and it opened; tab to "Entwickler" and nothing; tab to "Unternehmen" and it
   * opened again. Each close was cancelling the open that had already happened, leaving the next
   * one unopposed.
   *
   * A timer the open can cancel is the standard shape for this, and the ordering it encodes is the
   * real intent: an item claiming focus always beats a queued departure, because the departure was
   * only ever provisional.
   */
  const closeTimer = useRef<number | undefined>(undefined);

  const openDropdown = (index: number, item: NavItem) => {
    if (closeTimer.current !== undefined) {
      window.clearTimeout(closeTimer.current);
      closeTimer.current = undefined;
    }
    setHovered(index);
    setOpenMenu(item.dropdown ? item.name : null);
  };

  const closeAll = () => {
    if (closeTimer.current !== undefined) window.clearTimeout(closeTimer.current);
    closeTimer.current = undefined;
    setHovered(null);
    setOpenMenu(null);
  };

  /* A stray timer outliving the component would call setState after unmount. */
  useEffect(() => () => window.clearTimeout(closeTimer.current), []);

  return (
    <nav
      onMouseLeave={closeAll}
      /*
       * Focus leaving the group closes it — decided a tick later, against `document.activeElement`
       * rather than against the event's `relatedTarget`.
       *
       * `relatedTarget` is null whenever focus moves programmatically or to a non-focusable
       * target, which reads as "focus left" and would close a menu the visitor is still inside.
       * Asking who actually holds focus once the browser has finished moving it answers the
       * question being asked rather than a proxy for it.
       *
       * The deferral is why `closeTimer` exists: see it above for the alternating-menu bug that
       * comes from letting this land after a neighbouring item has already opened.
       */
      onBlur={(event) => {
        const group = event.currentTarget;
        if (closeTimer.current !== undefined) window.clearTimeout(closeTimer.current);
        closeTimer.current = window.setTimeout(() => {
          closeTimer.current = undefined;
          if (!group.contains(document.activeElement)) closeAll();
        }, 0);
      }}
      className={cn("flex flex-1 items-center justify-center gap-1", className)}
    >
      {items.map((item, index) => {
        const open = () => openDropdown(index, item);

        const label = (
          <>
            {hovered === index ? (
              <motion.span
                layoutId="azm-nav-hover-pill"
                className="absolute inset-0 rounded-full bg-azm-ink/5"
                transition={{ type: "spring", stiffness: 380, damping: 32 }}
              />
            ) : null}
            <span className="relative z-10">{item.name}</span>
          </>
        );

        return (
          <div
            key={item.link}
            className="relative"
            onMouseEnter={open}
            /* `onFocus` as well as hover: a dropdown reachable only by pointer is not reachable. */
            onFocus={open}
          >
            {item.render ? (
              item.render({ className: NAV_LINK_CLASS, children: label })
            ) : (
              <a href={item.link} className={NAV_LINK_CLASS} onClick={onItemClick}>
                {label}
              </a>
            )}
            {item.dropdown ? (
              <NavDropdown open={openMenu === item.name}>{item.dropdown}</NavDropdown>
            ) : null}
          </div>
        );
      })}
    </nav>
  );
}

/**
 * The mobile bar. Same glass, same scroll response, laid out as a column so the expanded menu
 * pushes down from the header rather than floating detached from it.
 */
export function MobileNav({
  children,
  className,
  visible,
}: {
  children: React.ReactNode;
  className?: string;
  visible?: boolean;
}) {
  const reduceMotion = useReducedMotion();

  return (
    <motion.div
      animate={{ y: visible ? 8 : 0, paddingInline: visible ? 12 : 0 }}
      initial={false}
      transition={reduceMotion ? { duration: 0 } : RESIZE_SPRING}
      /*
        `w-full px-2`, not `max-w-[calc(100vw-1rem)]`. The upstream expression is a trap on any
        surface with a classic scrollbar: `100vw` measures the viewport *including* the scrollbar
        gutter, so the bar comes out wider than the space it has and the document scrolls sideways
        by 15px. Padding on a full-width box states the same intent and cannot be wrong.
      */
      className={cn("w-full px-2 lg:hidden", className)}
    >
      <motion.div
        initial={false}
        animate={{ opacity: visible ? 1 : 0 }}
        transition={{ duration: reduceMotion ? 0 : 0.25 }}
        aria-hidden="true"
        className="azm-glass pointer-events-none absolute inset-x-2 top-0 h-16 rounded-2xl"
      />
      <div className="relative flex w-full flex-col">{children}</div>
    </motion.div>
  );
}

export function MobileNavHeader({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex h-16 w-full items-center justify-between px-2", className)}>
      {children}
    </div>
  );
}

/**
 * The expanded mobile panel.
 *
 * `height: auto` in the animation rather than a fixed value, because the link list is driven by a
 * message catalogue and a hard-coded height is wrong the first time somebody adds a page. It is
 * paired with `overflow: hidden` so the content clips while the box is still opening instead of
 * spilling over the page beneath it.
 */
export function MobileNavMenu({
  children,
  className,
  isOpen,
}: {
  children: React.ReactNode;
  className?: string;
  isOpen: boolean;
}) {
  const reduceMotion = useReducedMotion();

  return (
    <AnimatePresence initial={false}>
      {isOpen ? (
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: "auto" }}
          exit={{ opacity: 0, height: 0 }}
          transition={{ duration: reduceMotion ? 0 : 0.3, ease: [0.16, 1, 0.3, 1] }}
          className="overflow-hidden"
        >
          {/*
            A heavier tint than the bar's, via the `--azm-glass-tint` override the class exposes.
            The bar overlays a 4rem strip and 72 % white is plenty; this panel overlays the hero
            headline at 56px, and display type showing through a menu is the difference between
            "glass" and "unreadable". Same material, more of it.
          */}
          <div
            className={cn(
              "azm-glass mt-2 flex w-full flex-col gap-1 rounded-2xl p-4 [--azm-glass-tint:oklch(1_0_0/0.95)]",
              className
            )}
          >
            {children}
          </div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}

/**
 * The hamburger.
 *
 * A real `<button>` with an `aria-expanded` and an accessible name. Upstream renders a bare icon
 * with an `onClick` on the SVG — not focusable, not announced, and not operable from a keyboard.
 */
export function MobileNavToggle({
  isOpen,
  onClick,
  label,
}: {
  isOpen: boolean;
  onClick: () => void;
  label: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-expanded={isOpen}
      aria-label={label}
      className="flex size-10 items-center justify-center rounded-full text-azm-ink transition-colors hover:bg-azm-ink/5"
    >
      {isOpen ? (
        <XIcon className="size-5" aria-hidden="true" />
      ) : (
        <MenuIcon className="size-5" aria-hidden="true" />
      )}
    </button>
  );
}

/* Re-exported so a call site composing the hybrid imports one module rather than two. */
export {
  NavDropdown,
  NavDropdownLink,
  NavDropdownItem,
  navDropdownLinkClass,
} from "@workspace/ui/components/navbar-menu";
