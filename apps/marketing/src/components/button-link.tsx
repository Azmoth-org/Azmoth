import { Button } from "@workspace/ui/components/button";

import { TransitionLink } from "@/components/transition-link";

/**
 * A button that is actually a link.
 *
 * It exists because `<Button render={<a href=… />}>` is a trap. Base UI's Button
 * defaults `nativeButton` to `true`, so rendering it as an anchor keeps
 * button semantics on an element that is not a button — the browser then reports
 * `role="button"` for something that navigates, which breaks the middle-click,
 * open-in-new-tab and copy-link affordances a link is supposed to have, and reads
 * wrong to a screen reader. Base UI warns about it at runtime; the site had eleven
 * of these before this component existed.
 *
 * Setting `nativeButton={false}` once here means the twelfth call site cannot get it
 * wrong either.
 *
 * `external` picks the element: the product app is a different origin, so those
 * links must be a plain `<a>` — the locale-aware `Link` would try a client-side
 * transition inside this app and land on a 404.
 *
 * The internal branch renders `TransitionLink` rather than the bare `Link`. That is what makes the
 * page-transition curtain a property of *navigating this site* instead of a property of the header
 * that happens to own it: a visitor who leaves the home page from the closing call-to-action gets
 * the same sweep as one who used the navigation. `TransitionLink` still renders the locale-aware
 * `Link` underneath, so prefetching and href resolution are unchanged.
 */
export function ButtonLink({
  href,
  external = false,
  newTab = false,
  children,
  ...props
}: Omit<React.ComponentProps<typeof Button>, "render"> & {
  href: string;
  external?: boolean;
  /**
   * Open in a new tab, with the security attributes that have to travel with it.
   *
   * A separate flag from `external` rather than implied by it, because the two outbound
   * destinations want opposite behaviour. The product app is a *handoff* — somebody clicking
   * "Anmelden" is done with the brochure, and stranding them with two tabs is clutter. The
   * documentation is a *reference* — they are reading it against this page, and taking the page
   * away from them loses their place in the argument.
   *
   * `rel` is not optional here. `noopener` denies the new document a `window.opener` handle back
   * into this one, and `noreferrer` keeps this site's URL out of its request headers. Setting
   * `target` without them is the reverse-tabnabbing footgun, and the point of centralising this
   * on the component is that a call site cannot remember only half of it.
   */
  newTab?: boolean;
}) {
  const anchor = newTab ? (
    <a href={href} target="_blank" rel="noopener noreferrer" />
  ) : (
    <a href={href} />
  );

  return (
    <Button
      nativeButton={false}
      render={external ? anchor : <TransitionLink href={href} />}
      {...props}
    >
      {children}
    </Button>
  );
}
