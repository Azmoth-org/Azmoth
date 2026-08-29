<!-- impeccable:product-schema 1 -->

# PRODUCT.md — SILKDEV

**Voice directive (verbatim):**
> "I want to be the agency that provides every technical solution, dev, design in tunisia or otherwise. If it can be done it will be done. I want to add services and tools for users dynamically, I want my system to evolve and create new products and trends dynamically based on the newest hypes and trend and suggest / create if for customers (maybe even go on as to promote it). I want silkdev to be the money printing machine that will fund my other projects."

## Platform
Website + customer portal at silkdev.vercel.app (production), locale-routed (en/fr/ar, RTL for ar). Next.js 16 App Router, Tailwind v4, Prisma + Neon Postgres, better-auth, ZeptoMail transactional email, assistant-ui chat, Tailark dusk design kit.

## Stack
Next.js 16 · Tailwind v4 · Prisma 7 (Neon) · better-auth · ZeptoMail · Vercel · assistant-ui (official Thread) · AI SDK (chat via Vercel AI Gateway free tier — primary `deepseek/deepseek-v3.1` + free-eligible fallback chain) · Tailark dusk blocks (free OSS kit) · shadcn primitives.

## Users
- **Primary: project owners** — Tunisian SMBs and international founders who need technical work done (dev, design, AI) and can't or won't build it in-house. They arrive via search (ar/fr/en), the AI intake chat, or the portal.
- **Secondary: the SILKDEV team** (agency console) — reviewing briefs, promoting briefs to projects, moving stages, and (manually) extending the service catalog as trends emerge.

## Product Purpose
Be the agency that can build *anything* technical — the answer to "can you do X?" is always "yes, and here's how." The site's job is to convert visitors into intake-chat conversations with as little friction as possible; every project then lives in a client portal with a planner, notifications, and an AI rep that knows the project and the client. SILKDEV funds the founder's other products (SILKLEARN, LucaP, SILKLABS, SILKGUILD).

## Positioning
"An AI development agency in Bizerte, Tunisia — software you can rely on, from Bizerte to the world." The wedge: a working AI on the homepage (the intake chat IS the demo), trilingual coverage, and a live portal where clients watch the work happen. Not a commodity dev shop: the studio that sells the shovels.

## Operating Context
- **Funnel**: search/marketing → homepage (chat CTAs everywhere) → AI intake chat → brief → portal (planner + rep chat + notifications + email).
- **Curated catalog, manual evolution (current)**: the 6 service offerings are a curated catalog; new services are added manually by the team as trends emerge. The chat *routes* users to the catalog — it does not auto-create services (aspiration, not today).
- **Clients are real, claims are real**: metrics shown are true (4+ years, Google 5.0, 6 services, 4 products). Nothing fabricated.

## Capabilities & Constraints
- Capabilities: intake chat with calendar booking; brief → project promotion; stage/task pipeline; in-app + email notifications; AI project rep with client-memory; trilingual content; blog synced from the Framer CMS; ZeptoMail transactional email; per-project quoting (no public prices).
- Constraints: no OAuth providers (email/password + anonymous only); no CI (manual CLI deploys); repo private; all AI chat (intake + portal rep) runs through the Vercel AI Gateway free tier with a per-request fallback chain of free-eligible models (chain + auth in `src/lib/ai-gateway.ts`; env: `AI_GATEWAY_API_KEY`, optional `AI_GATEWAY_MODELS`); migration changes apply via `prisma migrate deploy` at build.

## Brand Commitments
- **The Anything Rule.** "If it can be done, it will be done" — scope is never declined, it's shaped.
- **The Honest-Funnel Rule.** Every claim on the site is verifiable; no invented testimonials, no fake metrics, no fabricated endorsements (client logos are real clients).
- **The Demo-First Rule.** Every service ships with a working demo — the intake chat is the AI support demo, SILKLEARN is the knowledge-AI demo, the portal is the delivery demo.
- **The Rarity Rule.** Violet signal is scarce and means "act here."

## Evidence on Hand
- Google Business Profile: **5.0 rating** (Menzel Bourguiba, Tunisia) — verified live on the site.
- 4+ years in business · 4 products launched · 3 locales supported (homepage stats).
- 9 blog articles (2026-07 series) synced live from the Framer CMS via `sync-blogs.mjs`.
- Real clients: IPS, Luca Pacioli, Wolves Gym, Meridian, Podomus (logos in the hero carousel + services page).
- Products: SILKLEARN (live), SILKLABS, SILKGUILD, LucaP — with real icon assets.
- Working portal: planner (tasks/milestones), notifications (bell + ZeptoMail emails), AI project rep with `ClientMemory`.
- **Absences (must NOT be fabricated):** no published client testimonials on-site (reviews section renders only when real reviews exist); no case-study metrics (the "15x/3x" numbers were removed as unverifiable); no headcount/revenue claims; no pricing (per-project quoting only); no social follower counts.

## Product Principles
1. **The Anything Rule** — never decline scope; shape it.
2. **The Honest-Funnel Rule** — every CTA's job is the intake chat; every claim is real.
3. **The Live-Proof Rule** — the AI must be usable on every page that mentions AI.
4. **The Portal-First Rule** — clients watch work happen; the portal is retention.
5. **The Memory Rule** — the AI rep remembers the client; every conversation compounds context.
6. **The Trend-Pulse Rule** — the catalog evolves as trends emerge (manually today, but deliberately).

## Accessibility & Inclusion
- Trilingual (ar RTL / fr / en), native Arabic support.
- Intentional reduced-motion handling (kill loops, complete fades) — no global 0.01ms kill.
- Known gap (tracked): white-on-violet button text is 4.32:1 (fails WCAG AA) — accent darkening to `#5a52e0` (5.65:1) is the planned fix; touch targets below 44px in the portal (task checkboxes, icon buttons) need enlarging.
- The custom cursor is hover-gated (`(hover: hover)`) and never hides the native cursor on touch.
