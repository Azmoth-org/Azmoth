/**
 * Every number this site prints about the engine, in one place — and the reason it
 * is a module rather than prose in the message catalogue.
 *
 * `apps/engine/tests/test_published_numbers.py` exists because this product shipped,
 * for weeks, a customer-facing PDF and a partner contract quoting rule counts that
 * were wrong by an order of magnitude. Every one of those figures had been true when
 * it was written. The conclusion that test draws is the one that governs this file:
 * **a number written into prose is a claim with no mechanism to stay true**, so
 * shipped text may not contain one unless something fails a build when it drifts.
 *
 * A marketing site is the most public shipped text there is, and this one's entire
 * pitch is "we do not assert what we cannot prove". Printing a stale rule count under
 * that headline is not a small inaccuracy; it is the product's central claim failing
 * on its own home page.
 *
 * So the constants live here, the German copy in `messages/de.json` carries ICU
 * placeholders instead of digits, and that same Python test pins the values below to
 * what `Pipeline().rule_coverage()` computes. Changing a rule set without changing
 * this file turns the engine's own suite red.
 *
 * Verified against the engine on 2026-08-31:
 *
 *     enforced_rule_count       858
 *     total_constraint_rule_count 894
 *     catalog                   2192 Ziffern (goae_official_snapshot_2026-07-25)
 *     Ziffern named by >= 1 enforced rule  358
 */

/** Rules that may actually suppress a position right now. `enforced_rule_count`. */
export const ENFORCED_RULE_COUNT = 858;

/** Every constraint rule loaded, enforced or not. `total_constraint_rule_count`. */
export const CONSTRAINT_RULE_COUNT = 894;

/** GOÄ positions in the loaded catalog snapshot. */
export const CATALOG_ZIFFER_COUNT = 2192;

/** Catalog positions named by at least one enforced rule. The honest coverage figure. */
export const ZIFFERN_UNDER_RULE_COUNT = 358;

/**
 * Median end-to-end latency for one invoice, in milliseconds.
 *
 * From `docs/performance_baseline.md` — median of seven cold runs across the three
 * golden cases, 75.8 / 76.8 / 79.5 ms, on a 2020 laptop with a browser open.
 *
 * **Per invoice, not per position**, and it is worth being pedantic about which:
 * a rate quoted per position would be roughly eight times smaller and would read as
 * the more impressive number, which is exactly why it would be the dishonest one.
 * The measurement is of a whole delivery going through the pipeline.
 */
export const LATENCY_MS_PER_INVOICE = 80;

/** Share of loaded constraint rules the engine actually enforces — "96 %". */
export const ENFORCED_RULE_SHARE = ENFORCED_RULE_COUNT / CONSTRAINT_RULE_COUNT;

/** Share of the GOÄ catalog any enforced rule speaks to — "16 %". The weak spot, stated. */
export const CATALOG_COVERAGE_SHARE = ZIFFERN_UNDER_RULE_COUNT / CATALOG_ZIFFER_COUNT;

/**
 * German number formatting, fixed to `de-DE` rather than the request locale.
 *
 * The site is single-locale and statically prerendered, so there is no request locale
 * to read at render time anyway — but naming it explicitly is what keeps a thousands
 * separator from silently becoming a comma if a second locale ever arrives.
 */
const de = new Intl.NumberFormat("de-DE");
const dePercent = new Intl.NumberFormat("de-DE", {
  style: "percent",
  maximumFractionDigits: 1,
});

/**
 * The values the message catalogue interpolates, pre-formatted.
 *
 * Percentages are *computed* from the counts, not written down: "96 %" and "858 von
 * 894" are the same claim twice, and the failure mode this whole file guards against
 * is exactly the version where one of the two gets updated.
 */
export const engineFacts = {
  regelnDurchgesetzt: de.format(ENFORCED_RULE_COUNT),
  regelnGesamt: de.format(CONSTRAINT_RULE_COUNT),
  regelnAnteil: dePercent.format(ENFORCED_RULE_SHARE),
  katalogZiffern: de.format(CATALOG_ZIFFER_COUNT),
  katalogGeprueft: de.format(ZIFFERN_UNDER_RULE_COUNT),
  katalogAnteil: dePercent.format(CATALOG_COVERAGE_SHARE),
  laufzeitMs: de.format(LATENCY_MS_PER_INVOICE),
} as const;
