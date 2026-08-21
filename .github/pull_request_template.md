<!--
Keep this short and honest. A reviewer needs to know what you verified, not what you typed —
the diff already says what you typed.
-->

## What and why

<!-- One or two sentences. Why the change is needed, not a restatement of the diff. -->

## Verified

<!-- Paste the actual output lines. "Tests pass" is not evidence; "570 passed" is. -->

- [ ] `cd apps/engine && .venv/bin/python -m pytest` → <!-- e.g. 570 passed -->
- [ ] `pnpm turbo typecheck lint build` → <!-- e.g. 6/6 successful -->
- [ ] `souffle` was on PATH, so the rules-engine tests **ran** rather than skipped
      <!-- a green run without it tested almost nothing; check the skip count -->

## Checklist

- [ ] **Synthetic data only.** No patient data, no real invoice, not even in a local test.
- [ ] No credential, token or key added anywhere — including in a test fixture.
- [ ] The branch name and commit messages follow `CONTRIBUTING.md`.
- [ ] One reviewable idea. If the description needs "and", this should be two PRs.

### If the contract changed (a Python schema or an endpoint)

- [ ] Regenerated **in this order** and committed both outputs:
      `python scripts/export_openapi.py` then `pnpm generate:contracts`
- [ ] `packages/contracts/typescript/schema.ts` was **not** hand-edited.

### If `apps/web` changed

- [ ] No monetary arithmetic in the frontend. Amounts are printed exactly as the engine returned
      them — not parsed, not summed, not re-rounded, not re-localised.
- [ ] No field typed that the OpenAPI document does not have.

### If `logic/` or `data/` changed — needs a second approver

- [ ] The ASP objective ordering (`@5/@4/@3/@2/@1`, revenue **last**) is unchanged, and no hard
      constraint became a weighted term.
- [ ] No unverified rule was deleted, and no `verified` flag was flipped without a named reviewer
      and a date.
- [ ] The catalog JSON and rule CSVs were not hand-edited (corrections go through
      `data/catalogs/goae_current/overrides.json`).
- [ ] Golden snapshots in `logic/tests/golden/` are unchanged.
      **If one moved:** say which number changed, from what to what, and why the new value is
      correct. Do not regenerate a snapshot to make the suite pass.

## Risk

<!--
Anything a reviewer should look at hardest. If this touches money, a rule, the solver objective or
the compliance posture, say so here and in the PR title so it reaches the right reviewer.
-->
