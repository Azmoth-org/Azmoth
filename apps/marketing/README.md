# `apps/marketing` — the public site

A statically prerendered Next application whose only job is to hand a visitor to the product. It
holds no data, has no database and renders one locale (`de`).

Most of what you would normally put in a README of this kind is in the files themselves — every
component here carries a block comment explaining why it is built the way it is, and those comments
are the authority. This file covers the two things that live *between* files and therefore cannot
be written down in any one of them: **what the home page is trying to do, in order**, and **the rule
about numbers.**

---

## The rule about numbers

**No figure appears in shipped copy unless something fails a build when it drifts.**

This is not a style preference. This product shipped, for weeks, a customer-facing PDF and a partner
contract quoting rule counts that were wrong by an order of magnitude — every one of them true when
it was written. So:

- Numbers live in [`src/lib/engine-facts.ts`](src/lib/engine-facts.ts) as constants.
- `apps/engine/tests/test_published_numbers.py` pins those constants to what `Pipeline()` actually
  computes. Changing a rule set without changing that file turns the engine's suite red.
- German copy in [`messages/de.json`](messages/de.json) carries ICU placeholders — `{regeln}`,
  `{laufzeit}`, `{katalogAnteil}` — and **never a digit**.

The current values, verified against the engine on 2026-09-12 (see
[`docs/content/coverage-sprint-plan.md`](../../docs/content/coverage-sprint-plan.md)):

| Fact | Value | Constant |
|---|---|---|
| Rules that can suppress a position | 944 | `ENFORCED_RULE_COUNT` |
| Constraint rules loaded | 980 | `CONSTRAINT_RULE_COUNT` |
| GOÄ positions in the catalog snapshot | 2 343 | `CATALOG_ZIFFER_COUNT` |
| Positions named by ≥ 1 enforced rule | 383 | `ZIFFERN_UNDER_RULE_COUNT` |
| Median latency per delivery | 80 ms | `LATENCY_MS_PER_INVOICE` |

Shares (96 %, 16,3 %) are **computed** from those counts, never written down — "96 %" and "944 von
980" are the same claim twice, and the failure mode is the version where one gets updated.

### What this rules out

The site has no testimonials, no named reference customers, no "€X gespart" figures and no pricing.
Not because those would be ineffective — because none of them exists to cite. There is no pilot
customer in this repository and `docs/MONETIZATION.md` still has its price fields blank.

Inventing them would be a §5 UWG problem for a medical billing product before it was a taste
problem, and it would break the page's own argument: the headline is that Azmoth does not assert
what it cannot prove.

The substitute is in [`src/components/metrics.tsx`](src/components/metrics.tsx) — three numbers a
prospect can check, including the unflattering one (16,3 % catalog coverage) at the same type size
as the other two. See that file's header for why the unflattering one converts better than a
testimonial would.

**Before adding any figure to this site, ask where it is pinned.** If the answer is "a slide deck",
it does not go on the page.

---

## Home page composition

[`src/app/[locale]/(marketing)/page.tsx`](src/app/[locale]/\(marketing\)/page.tsx) is one file of
numbered sections. The order is the **objection order** — the sequence a German billing centre
actually raises doubts in — not a feature order:

| # | Section | Job | Anchor |
|---|---|---|---|
| 1 | `Hero` + `PipelineFlow` | What is this, in one look | — |
| 2 | `TrustBand` | Believable in a second, deliberately under-designed | — |
| 3 | `Vergleich` | Their situation, then what changes | — |
| 4 | `Workflow` | Three steps, one line each | `#loesung` |
| 5 | `Buckets` + `HeroMockup` | The three verdicts, then the report they produce | `#kategorien` |
| 6 | `Zahlen` | Checkable numbers, where a testimonial would be | `#zahlen` |
| 7 | `Sicherheit` | Where the data lives — asked *before* price | `#sicherheit` |
| 8 | `Audiences` | Qualify: billing centre / vendor / physician | — |
| 9 | `Pilot` | The ask | `#pilot` |
| 10 | `ApiTeaser` | The technical evaluator's track | `#api` |
| — | `ClosingCta` | Repeat the one CTA | — |

Section 7 sitting before 9 is the only ordering choice worth arguing about, and the reason is in that
function's comment: a Datenschutzbeauftragte's sign-off gates the deal, so answering "where does the
data live" after asking for a signature is answering it too late.

---

## Animation: which layer, and why

The site uses three mechanisms, and picking the wrong one has measurably cost this page its Largest
Contentful Paint before. The decision rule:

| Where | Mechanism | Why |
|---|---|---|
| **Above the fold** | CSS keyframes (`.azm-enter`, `.azm-stage`, `.azm-chip`, `.azm-connector`) | Starts when the stylesheet parses. No bundle, no hydration. A `<Reveal>` here moved LCP from 320 ms → 1050 ms. |
| **Below the fold** | `<Reveal>` / `<RevealGroup>` (`motion`) | CSS cannot observe the viewport portably yet. Free down here — hydration has long finished. |
| **Hover** | CSS (`.azm-lift`) | `whileHover` would make eighteen cards client components to move them 4 px. |

Two hard rules inside that:

1. **Animate `opacity` and `transform` only.** No `filter`, no `width`, no `background-position`.
   Non-composited properties re-run paint every frame; Lighthouse flags them, and above the fold the
   frames land in the window the visitor is waiting for the headline.
2. **The `<h1>` never animates.** Chrome fixes LCP candidacy at an element's *first* paint, so
   anything starting at `opacity: 0` is excluded from the metric permanently — the number improves
   while the headline appears no sooner.

`prefers-reduced-motion` resolves entrances to their **end state** rather than disabling them.
Disabling an animation with a `both` fill leaves the element at `opacity: 0` forever, which is how
"respects reduced motion" usually ships as "the content is invisible".

---

## Adding a `@workspace/ui` component

**You must also add it to the `@source` list in [`src/app/globals.css`](src/app/globals.css).**

`packages/ui` holds sixty-odd shadcn components because `apps/web` is a product; this site mounts
nine and names them explicitly. Scanning the whole package generated 195 kB of CSS, 169 kB of it
utilities for a sidebar, calendar and command palette this site has no route that renders — all
render-blocking in front of the hero. Naming the nine brings it to 64 kB.

The failure mode when you forget is silent and reads as a styling bug rather than a build error: the
component renders with its class names intact and no rules behind them.

---

## Local development

```bash
pnpm dev        # localhost:3001
pnpm build      # static prerender of every route
pnpm start      # serve the build
pnpm typecheck
pnpm lint
```

Two environment variables, both read at **build** time because every page is statically
prerendered — changing either means a rebuild, not a container restart:

| Variable | Default | Used for |
|---|---|---|
| `APP_URL` (or `NEXT_PUBLIC_APP_URL`) | `http://localhost:3000` | Every link into the product — `/login`, `/signup`, `/demo` |
| `NEXT_PUBLIC_DOCS_URL` | `https://docs.azmoth.com` | The developer track, header and footer |

Analytics is **off unless configured** (`NEXT_PUBLIC_ANALYTICS_PROVIDER` = `plausible` \| `umami`,
plus `_SRC` and `_SITE_ID`). Both providers are cookieless and store nothing on the device, which is
why there is no consent banner — § 25 TDDDG governs storing or reading on a terminal device, and
neither does. See [`src/lib/analytics.ts`](src/lib/analytics.ts) for why this is not GA.

---

## Things that are deliberately absent

Each of these was asked for at some point and declined for a reason recorded in the code:

- **A file-upload demo on this origin.** PADnext carries patient billing data; this site has no
  auth, no AVV and no processing basis. The product app's `/demo` needs no account and no upload —
  that is where the CTA points.
- **A booking embed.** `cal.com/azmoth` returns 404. `src/lib/site.ts` documents the earlier version
  of this mistake: `api.azmoth.com` was linked from three places and had no DNS record at all, so
  the link a technical evaluator was most likely to click was the one that proved the opposite of
  the section's argument.
- **Vendor logos in the compliance row.** Naming AWS and Neon in the site's own type is
  infrastructure disclosure. Their marks next to "DSGVO-konform" edges toward implying they endorse
  the compliance claim.
- **A hidden navigation.** Impressum and Datenschutz must be reachable from every page (§ 5 DDG).
