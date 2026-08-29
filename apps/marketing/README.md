# Silkdev Website

Next.js static site for [silkdev.com.tn](https://silkdev.com.tn) — extracted from Framer.

## Tech Stack

- **Next.js 16** (App Router, SSG)
- **TypeScript 5**
- **Tailwind CSS v4**
- **pnpm**

## Pages

| Route | Description |
|-------|-------------|
| `/` | Homepage — Hero, Story, Pivot, SILKLEARN, CTA |
| `/services` | Web development, SEO & design services |
| `/portfolio` | Project showcase |
| `/blog` | Blog listing (latest + all) |
| `/blog/[slug]` | Blog detail with HTML content |
| `/pricing` | Pricing plans & options |
| `/faq` | FAQ accordion |
| `/about` | About the studio |
| `/contact` | Contact form & info |

## Development

```bash
pnpm install
pnpm dev       # local dev server
pnpm build     # production build
pnpm start     # serve production build
```

## Deployment (Vercel — Free Tier)

1. Push this repo to GitHub/GitLab
2. Import it on [vercel.com](https://vercel.com/new)
3. Framework preset: **Next.js** (auto-detected)
4. Deploy — Vercel handles everything

The site uses SSG (Static Site Generation), so it's fully compatible with Vercel's free tier (100 GB bandwidth, 6000 build minutes/month).

## Data

Blog content lives in `src/data/blogs.json` — a JSON array exported from the Framer CMS. To update, edit that file and rebuild.

## Original Framer Project

The original Framer site is managed through `silkdev-framer-api/` (sibling directory), which uses the Framer Server API for CMS and content management. This Next.js port is a static extraction — there's no Framer dependency.
