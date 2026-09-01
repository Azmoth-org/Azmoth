# `apps/docs`

The Azmoth documentation site — [Fumadocs](https://fumadocs.dev) on Next.js, served at
`docs.azmoth.com`. Prose for an integrator and for a billing centre; it holds no data of its own
and talks to nothing.

It replaced `/api-dokumentation` on the marketing site. That page was a single orientation screen
that could not grow without turning a brochure into a manual, and the marketing app has no search,
no sidebar and no MDX pipeline to grow it with.

## Layout

| Path | What it is |
|---|---|
| `content/docs/` | The prose. MDX plus a `meta.json` per directory for sidebar order and titles. |
| `source.config.ts` | The collection definition and the MDX pipeline. `fumadocs-mdx` reads this, not `next.config.ts`. |
| `.source/` | Generated from the above on install and on every build. Not committed. |
| `lib/source.ts` | The loaded content tree — page URLs, the sidebar, `generateStaticParams`. |
| `lib/layout.shared.tsx` | The navbar: the Azmoth lockup and the outbound links. |
| `app/(docs)/` | The documentation shell and the catch-all that renders every page. |
| `app/globals.css` | Where `DESIGN.md` and Fumadocs meet — see the header comment in that file. |
| `mdx-components.tsx` | The components an MDX page can use without importing anything. |

## Running it

```sh
pnpm install                 # generates .source/ via postinstall
pnpm --filter docs dev       # http://localhost:3002
```

```sh
pnpm exec turbo run build --filter=docs
```

Node 22 or newer — Fumadocs requires it, and `package.json` says so.

## Writing a page

Add an `.mdx` file under `content/docs/`. Frontmatter takes `title` (required), `description` and
`icon` — the icon name is resolved against [lucide](https://lucide.dev)'s exported set by
`lib/source.ts`, so `icon: Plug` is enough.

Sidebar order comes from `meta.json` in the same directory; a page not listed there is appended
alphabetically. `---Label---` in a `pages` array renders as a section separator.

**Prose is German. Code, endpoints and field names are English** — they are what an integrator
types, and translating an identifier makes it wrong.

## Design

The site is not a themed template: `app/globals.css` repoints every `--color-fd-*` token Fumadocs
reads at a token from `@workspace/ui`, which is where `DESIGN.md` lives. No component is
overridden, and a Fumadocs component nobody has used yet is already on brand. Read the header
comment in that file before changing a colour.

The site is light-only, like `apps/web` and `apps/marketing` — one visitor walks across all three
origins, and a dark reference page after a light marketing page does not read as the same company.
There is no theme switch and no `.dark` block; `app/globals.css` names the three edits that would
bring one back.

## Deploying to Vercel

The site is a third Vercel project in this repository, alongside `web` and `marketing`. Vercel
supports several projects per repo; each one is a different **Root Directory** on the same Git
connection.

1. **New Project** → import the same Git repository → **Add**.
2. **Root Directory**: `apps/docs`. Leave "Include files outside the root directory" **on** — the
   app consumes `@workspace/ui` as source from outside its own tree, and `next.config.ts` sets
   `outputFileTracingRoot` to the monorepo root for the same reason.
3. **Framework Preset**: Next.js. **Build Command** and **Install Command**: leave as detected —
   Vercel runs `pnpm install` at the workspace root, which triggers this package's `postinstall`
   and writes `.source/`.
4. **Node.js Version**: 22.x. The default is usually right, but Fumadocs requires 22 and a project
   pinned to 20 fails at install rather than at build, which is a confusing place to find out.
5. **Environment Variables** (Production, Preview and Development — all three are read at build
   time, because every page is prerendered):

   | Name | Value |
   |---|---|
   | `NEXT_PUBLIC_DOCS_URL` | `https://docs.azmoth.com` |
   | `NEXT_PUBLIC_SITE_URL` | `https://azmoth.com` |
   | `APP_URL` | `https://app.azmoth.com` |

6. **Domains** → add `docs.azmoth.com`, and create the `CNAME` Vercel shows you at the registrar
   holding `azmoth.com`. Do not add an apex or `www` record here; those belong to the marketing
   project.
7. **Ignored Build Step** (Settings → Git), so a marketing-only commit does not rebuild this
   project:

   ```sh
   npx turbo-ignore docs
   ```

8. On the **marketing** project, set `NEXT_PUBLIC_DOCS_URL` to `https://docs.azmoth.com` as well —
   its header, footer and both API calls to action resolve against it, at build time. Redeploy it
   once after setting the variable, or the links keep the compiled-in default.

### If it is deployed the way the rest of the stack is

Production today is Docker behind Caddy on Azure (`docs/deploy/AZURE.md`), not Vercel. Putting this
app there instead means three things and no Vercel project: a `Dockerfile` modelled on
`apps/marketing/Dockerfile` — the build is the same shape, `output: "standalone"` with the
entrypoint at `apps/docs/server.js` — a service in `infra/docker/docker-compose.azure.yml`, and a
`docs.azmoth.com` block in `infra/docker/Caddyfile` reverse-proxying to it. None of that is in the
tree yet.
