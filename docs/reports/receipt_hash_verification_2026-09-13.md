# `receipt_hash` determinism verification

**Date:** 2026-09-13 · **Trigger:** UI observation on `/review` · **Engine:** working tree at
`40ac8f5` (branch `fix/factor-cap-citation-integrity`) · **Verdict:** no defect found; the observed
behaviour is the intended determinism guarantee.

## The observation

Two runs of the same fixture (`case_001_knee`), started at 00:41:34 and 01:00:53, produced two
proposals with different ids — `prop_69d9e05688c14b4c` and `prop_b87b1f9fc12c4b31` — and the
**same** `receipt_hash` prefix, `1fd67d6dd0e0df3814335305c…`. A third proposal visible on the same
page, `prop_89ed57378050462d`, had a different one.

This is exactly the contract `app/services/receipt.py` documents: two runs are supposed to collide
on the hash when — and only when — they were produced by the same catalog, rule tables, logic
programs, solver versions, policy and input facts. An identical hash for the same fixture is
correct. An identical hash for *different* fixtures, or a hash that failed to move when any of its
ten inputs changed, would not be.

## What is inside the hash

`receipt_hash()` (`apps/engine/app/services/receipt.py:50`) is a SHA-256 over a `ReceiptInputs`
model serialised through `canonical()`, in this order — ten fields, matching what the docstring and
`app/api/audit.py` describe:

1. `catalog_version`
2. `catalog_sha256`
3. `rules_version`
4. `rules_hash`
5. `logic_version`
6. `solver_version`
7. `rules_engine_version` (the Soufflé/Datalog engine version)
8. `policy` — `Settings.policy_fingerprint()`: `extraction_mode`, `unverified_rule_policy`,
   `base_factor_policy`
9. `facts` — the canonicalised clinical extraction (the input)
10. `output` — the canonicalised `Coding` (the invoice: charged Ziffern, factors, amounts, totals,
    blocked Ziffern and reasons)

`canonical()` (`apps/engine/app/core/canonical.py`) sorts dict keys, sorts lists by their own
canonical form (so Datalog's order-insensitive output doesn't count as a different answer), and
renders `Decimal` as its exact string rather than a `float` — never rounds or drops a cent.

## What is explicitly NOT inside

`canonical()` strips a fixed set of `VOLATILE_KEYS` before hashing, specifically because they differ
between two runs that mean the same thing: `proposal_id`, `created_at`, `timestamp`,
`generated_at`, `approved_at`, `started_at`, `finished_at`, every `*_ms` timing field, `request_id`,
`trace_id`, `correlation_id`, `run_id`, and `cached`.

Concretely, for the UI observation: `Pipeline.propose()` (`apps/engine/app/services/pipeline.py:272`)
generates `proposal_id` as `f"prop_{uuid.uuid4().hex[:16]}"` and `created_at` as
`datetime.now(timezone.utc)` **after** `receipt_hash()` has already been computed (on a fresh run)
or read back from the content-addressed cache (on a cache hit) — neither value is a parameter to
`receipt_hash()` at all. This is pinned by
`test_proposal_id_and_timestamp_are_not_among_the_ten_hashed_fields` in the new test module: it
inspects the function's own signature and asserts neither name is a parameter.

## Is the 00:41 / 01:00 pairing correct?

Yes. Two DRAFT proposals for `case_001_knee`, run ~19 minutes apart against an unchanged catalog,
rule tables, logic, solvers and policy, are supposed to hash identically — that is the entire point
of a content-addressed receipt: a reviewer can look at two receipts and know, without re-running
anything, whether they were produced by the same billing logic and the same input. The differing
`prop_89ed57378050462d` on the same page had a different receipt hash, consistent with it being a
different fixture or a different input.

## Verification performed

Added `apps/engine/tests/test_receipt_hash_determinism.py` (17 tests):

- **Same fixture, twice, in-process** — `pipeline.propose()` called twice for `case_001_knee`
  (second call is a cache hit): identical `receipt_hash`, non-identical `proposal_id` and
  `created_at`.
- **Same fixture, two independent `Pipeline` instances** (no shared cache) — same result, to rule
  out "it only matches because the cache remembered it" as an explanation.
- **Different fixtures** (`case_001_knee` vs. `case_002_cardiology`) — different hash. (Sanity-
  checked: temporarily hardcoding `receipt_hash()` to return a constant made this test, and 12
  others, fail — confirming the suite would have caught the "hash is constant" failure mode this
  test exists to rule out. The mutation was reverted; `git diff` on `receipt.py` is empty.)
- **Stale-cache guard** — mutate the input (`consultation.duration_minutes += 1`) and re-run on the
  *same*, already-warmed pipeline, no process restart: the cache key changes with the input, so the
  receipt hash changes too.
- **One parametrized case per hashed field** (11 cases covering the 10 fields — `facts` gets one
  structural perturbation and one one-cent perturbation) — each perturbs exactly one field against
  a fixed baseline and asserts the hash moves. Run directly against `receipt_hash()`, not through the
  pipeline, so each field is isolated from the other nine.
- **Purity** — `receipt_hash(**kwargs) == receipt_hash(**kwargs)` called twice with no pipeline, no
  cache, nothing measured in between.

No production code was changed to make these tests pass; all 17 passed against the existing
implementation on the first run.

## Full suite result

```
apps/engine$ python -m pytest
2269 passed, 7 skipped in 179.78s
```

The 7 skips are the suite's usual souffle-unavailable / benchmark skips (see
`apps/engine/tests/README.md`), unrelated to this change.

## Caveat, by design

Per the module's own docstring: the guarantee is one-directional. Same hash implies same catalog,
rules, logic, solver, policy and input — the converse does not hold **across engine versions**,
because the hash covers the canonical *response*, and a response schema change (e.g. adding
`BlockedCode.proof`) moves the hash even when the underlying billing decision is unchanged. A
receipt is comparable *within* one engine version, not across one. If cross-version comparability is
ever required, that is a deliberate, legally-reviewed change to what a receipt attests to (hashing a
narrower projection of the billing decision) — not a bug fix, and out of scope here.

## Disposition

No defect. No change to `app/services/receipt.py` or `app/core/canonical.py`. This report and the
new test module are the full deliverable for this investigation.
