# `@workspace/ui`

The shared component library. Every app in this monorepo imports its primitives from here, so a
button, a table row or a sidebar looks and behaves the same in `web` as it will in whatever is added
next.

## What is in here

`src/components/` holds the **complete shadcn/ui set** for the `base-luma` style — 55 components,
vendored as source rather than consumed as a package, which is how shadcn is designed to work: the
code is yours to read and to change.

`src/hooks/` holds the hooks those components need (`use-mobile`, used by `sidebar` and `drawer`).
`src/lib/utils.ts` holds `cn`. `src/styles/globals.css` holds the theme tokens, the light and dark
palettes, and the print stylesheet.

**`logo.tsx` is the one component here that is not shadcn.** It is the Azmoth lockup — the monogram
beside the wordmark — and it lives here rather than in an app because three surfaces draw it:
`apps/marketing`, `apps/docs`, and anything added next. Its wordmark is 5.6 kB of inlined path data,
which is exactly the kind of asset that goes quietly out of step when it exists in two places. It
does have one requirement an app must meet: the monogram is a `mask-image` at the origin-relative
path `/brand/azmoth-mark.png`, so every app rendering it must serve that file from its own
`public/`. `scripts/build-brand-assets.mjs` writes it into each of them, and adding an app means
adding it to that script's `TARGETS`.

## Using a component

```tsx
import { Button } from "@workspace/ui/components/button"
import { Sidebar, SidebarProvider } from "@workspace/ui/components/sidebar"
import { useIsMobile } from "@workspace/ui/hooks/use-mobile"
import { cn } from "@workspace/ui/lib/utils"
```

The `exports` map in `package.json` publishes `./components/*`, `./hooks/*`, `./lib/*` and
`./globals.css`, so nothing needs an index file and nothing needs a build step — Next transpiles the
source directly.

A new app needs three things: `"@workspace/ui": "workspace:*"` in its dependencies,
`@import "@workspace/ui/globals.css"` in its root layout, and a `components.json` whose `ui` alias
points at `@workspace/ui/components` (copy `apps/web/components.json`).

## Adding or updating a component

Run the CLI **from this package**, so the files land in `src/components/` and the dependencies land
in this `package.json`:

```sh
cd packages/ui
pnpm exec shadcn add <name>            # add one
pnpm exec shadcn add <name> --overwrite  # pull the latest version of one already here
pnpm exec shadcn search @shadcn --limit 300   # what exists
```

`--overwrite` replaces the file wholesale, **including any comment written here**. Two components
carry local documentation that a blind overwrite would drop:

- `skeleton.tsx` — why it never stands in for a number.

Check `git diff` after an overwrite and put anything like that back.

`form` is not in this style: `base-luma` replaces it with `field.tsx`, which covers the same ground
(`Field`, `FieldLabel`, `FieldError`, `FieldGroup`) without requiring `react-hook-form`.

## Lint

`carousel.tsx` and `hooks/use-mobile.ts` each trip `react-hooks/set-state-in-effect` as a **warning**.
Both are upstream registry code, unmodified. They are deliberately left alone: patching vendored
components makes the next `shadcn add --overwrite` a merge conflict, and the rule is advisory here —
neither is on a hot path.
