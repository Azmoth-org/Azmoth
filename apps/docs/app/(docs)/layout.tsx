import { DocsLayout } from "fumadocs-ui/layouts/docs";

import { baseOptions } from "@/lib/layout.shared";
import { source } from "@/lib/source";

/**
 * The documentation shell: navbar, sidebar tree, search.
 *
 * It is a route group — `(docs)` — rather than a `/docs` segment, which is the same decision
 * `lib/source.ts` explains from the other side. This application *is* `docs.azmoth.com`, so the
 * shell wraps the root and the landing page is `/`, not `/docs`. The group exists so that a
 * future route that must not carry the sidebar (an OG image handler, a redirect) can sit outside
 * it without being unwrapped case by case.
 */
export default function Layout({ children }: { children: React.ReactNode }) {
  return (
    <DocsLayout
      tree={source.pageTree}
      {...baseOptions()}
      sidebar={{
        /*
         * Fumadocs hides the sidebar's own banner slot by default and renders the navbar title
         * above it on desktop; nothing further is needed here. `collapsible` stays on — a
         * reference page with a wide response table is exactly when a reader wants the tree out
         * of the way.
         */
        collapsible: true,
      }}
    >
      {children}
    </DocsLayout>
  );
}
