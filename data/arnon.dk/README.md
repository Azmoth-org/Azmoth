# arnon.dk — a scraped reference corpus

Sixty-one articles from [arnon.dk](https://arnon.dk), the blog of **Arnon Shimoni**, scraped by
`scrape_arnon.py` in this directory. Mostly SaaS billing, pricing architecture and entitlements, with
some GPU-database and product-management writing.

## ⚠ Provenance and licence

**This is somebody else's work.** It is retained here as a reference the design of our billing system
cites, not as content of ours. It carries no licence granting redistribution, so:

- do not republish it, quote it at length in customer-facing material, or ship it in any artefact;
- attribute it where its reasoning is used — every citation in this repository names the article file
  and the author;
- treat a takedown request as immediately actionable.

`.venv/` beside it is git-ignored (352 MB of Scrapling and its dependencies) and is not part of the
repository.

## What it was used for, and what it was not

It is cited in the design of the billing system as a source of **principles**. Three of them:

| Idea | Article | Where it landed |
|---|---|---|
| Entitlement is separate from billing: ask "does this account have limit *N*", never "is it on plan gold" | [`why-you-should-separate-your-billing-from-entitlement`](data/markdown/why-you-should-separate-your-billing-from-entitlement.md) | `billing_plans.py` rule 3 — nothing outside that module branches on a tier |
| Pricing is append-only and versioned by SKU; never edit a price a customer is on | [`design-your-pricing-and-tools-so-you-can-adapt-it-later`](data/markdown/design-your-pricing-and-tools-so-you-can-adapt-it-later.md) | `plan_code` carries its revision (`starter-2026.08`), and the numbers are snapshotted onto the practice's row |
| Money is an integer count of its smallest subdivision | [`5-things-i-learned-developing-billing-system`](data/markdown/5-things-i-learned-developing-billing-system.md) | every amount in the schema and the API is `*_cents`, never a float or a decimal string |
| A free pilot that does not meter cannot be converted | [`pricing-ai-proofs-of-concept-free-pilots-will-kill-you`](data/markdown/pricing-ai-proofs-of-concept-free-pilots-will-kill-you.md) | the pilot plan is free **and** the meter runs in full from the first request |

**It contains no pricing for this product.** No invoice quotas, no tiers, no rates for GOÄ audit
tooling — it is a general blog, and nothing in it is a German market benchmark. The tier structure
and quotas come from [`docs/MONETIZATION.md`](../../docs/MONETIZATION.md), which is ours; the euro
amounts in `billing_plans.py` are explicitly-marked placeholders awaiting a business decision.

Anyone reading `docs/BILLING.md` and expecting this folder to have supplied numbers should read that
sentence again — it is the one thing about this corpus that is easy to assume and wrong.

## Regenerating

```
python scrape_arnon.py     # needs `scrapling`; writes data/articles.{json,csv} and data/markdown/
```

It reads the site's Yoast sitemaps, fetches each article, and writes one Markdown file per article
plus a flat metadata table. `REQUEST_DELAY` is 0.4 s; leave it there or raise it.
