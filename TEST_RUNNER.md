# `scripts/test-all.sh` — one command, one verdict

```bash
pnpm test                    # or: ./scripts/test-all.sh
```

Runs every test surface in the repository in dependency order and prints a single pass/fail
verdict. Exit status 0 means everything that could run, ran and passed.

The repository has five test surfaces and, before this script, no single place that ran them. CI
runs them as five GitHub jobs ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) — the right
shape for CI and the wrong shape for *"am I safe to commit?"*, because you cannot run a GitHub
matrix on a laptop. This is that second shape.

It is deliberately **not** a second definition of what the checks are. Every phase shells out to
the command that already owns it — `pnpm turbo typecheck`, `pytest`,
`scripts/e2e_partner_api.py` — so a check cannot pass here and fail in CI because this file
drifted. What lives in the script is the *order*, the *parallelism*, the *logs* and the *verdict*.

Nothing here requires Docker. Phase 4 needs a stack answering on two ports and says so plainly
when there isn't one; the other three phases run against the checkout.

---

## What it runs

| Phase | Checks | Parallel? | Typical |
|---|---|---|---|
| **1 — Fast checks** | Python lint (if configured), `turbo typecheck`, `turbo lint` | yes, 3 ways | ~30 s |
| **2 — Engine tests** | `pytest tests/ -rs`, then `pytest tests/test_golden_cases.py -v` | no, sequential | ~2–3 min |
| **3 — Builds** | `next build` for `web`, `marketing`, `docs` | yes, via turbo | ~1–3 min |
| **4 — E2E** | `scripts/e2e_partner_api.py --keep-practices` | n/a | ~40 s |

Phases run in order, and **the run stops at the first failing phase**. A type error makes a build
failure uninformative, and a broken engine makes an E2E failure a duplicate of a fact you already
have. Within a phase, every check still runs — one invocation shows you all of the type errors
*and* all of the lint errors.

### What is parallel, and why

**Phase 1 is parallel across the kinds of check, not across the apps.** `pnpm turbo` already fans
out over the six workspace packages internally and caches by content hash, so the background jobs
are the Python linter (when one is configured — see troubleshooting), `turbo typecheck` and
`turbo lint`. Running one turbo process per app would fight over `.turbo/` and lose the cache for
no gain. All of them are read-only over the same checkout, so there is nothing to race.

**Phase 2 is sequential, on purpose.** Both pytest invocations drive the same Soufflé binary and
the same catalog load, and `pytest-xdist` is not installed. Two concurrent pytest processes would
contend for `apps/engine/test.db` and interleave into an unreadable log, for no wall-clock saving.

**Phase 3 is one turbo invocation, not three `pnpm --filter` processes.** Turbo is the thing that
knows `web`, `marketing` and `docs` are independent and that `@workspace/ui` has to be typechecked
first. It runs them concurrently on its own *and* caches the result, so an unchanged app is a cache
hit rather than a second 90-second build. Three separate processes would lose that cache and race
each other for `.turbo/`.

**Phase 4 is a single script** that is itself ten sequential steps — it mints an API key, uses it,
meters it and revokes it, and the order is the test.

### Why the golden suite runs twice

`pytest tests/` already covers `tests/test_golden_cases.py`. The golden cases run again, on their
own line and in their own log, because they are the ones that assert the *billing numbers* against
[`tests/golden/oracle.py`](apps/engine/tests/golden/oracle.py) — an independent fee-schedule
calculation, not the engine. When they are the thing that broke, you want them named rather than
buried in 1,700 other results. It costs about four seconds.

---

## When to use it

| | |
|---|---|
| **Before every commit** | `pnpm test --fast` — phases 1 and 2, ~3 min. Catches the two things that actually break: a type error and a regressed rule. |
| **Before opening a PR** | `pnpm test` — everything, builds included. This is the local mirror of CI. |
| **Before a deploy** | `pnpm test` with a stack up, so phase 4 runs. Then [`scripts/preflight.sh`](scripts/preflight.sh), which checks the *deployment*, not the code. |
| **After changing a rule, the catalog or `logic/`** | `pnpm test --fast` at minimum. CI's logic guard will additionally require the golden snapshots to have been reviewed — see [`logic/README.md`](logic/README.md). |
| **After pulling main** | `pnpm test` once, to find out whether a failure is yours. |

---

## Running specific phases

```bash
./scripts/test-all.sh                # everything that can run here
./scripts/test-all.sh --fast         # phases 1 + 2 only, no builds. The pre-commit loop.
./scripts/test-all.sh --skip-e2e     # phases 1-3, never phase 4, even with a stack up
./scripts/test-all.sh --e2e-only     # phase 4 only, without probing first
./scripts/test-all.sh --no-color     # plain output (also implied by NO_COLOR=1 or a pipe)
./scripts/test-all.sh --help
```

There is no flag for a single phase 1 check or a single app's build, deliberately — those are one
command each already (`pnpm turbo typecheck --filter=web`), and a wrapper flag for each would be a
worse way to spell them.

### Environment

| Variable | Default | Notes |
|---|---|---|
| `E2E_ENGINE_BASE_URL` | `http://localhost:8000` | The same variable `e2e_partner_api.py` reads, so one export moves both halves. |
| `E2E_WEB_BASE_URL` | `http://localhost:3000` | Likewise. |
| `TURBO_CONCURRENCY` | turbo's default | Passed through. Set to `1` on a machine with less than ~4 GB free — see troubleshooting. |
| `PROBE_TIMEOUT` | `5` | Seconds to wait for the phase 4 stack probe. |
| `NO_COLOR` | unset | Any value disables colour. |

### Exit status

| | |
|---|---|
| `0` | Every phase that ran passed. |
| `1` | A phase failed. |
| `2` | Bad usage, or the environment cannot run the script at all (bash 3, no interpreter). |

A **skipped** phase 4 does not affect the exit code — a stack that is not up is a fact about the
machine, not a defect in the code. A phase 4 that *ran* and failed does.

### Logs

Every check writes its full output to its own file, and the transcript is saved without colour
codes, so a failure can be read after the terminal has scrolled:

```
logs/test-all-20260909-060455.log        the transcript, colour codes stripped
logs/test-all-20260909-060455/
    1-python-lint.log      only when a Python linter is configured
    2-typecheck.log
    3-eslint.log
    1-pytest-unit.log
    2-pytest-golden.log    only when the unit suite passed
    1-builds.log
    1-e2e.log              only when phase 4 actually ran
```

The numeric prefixes are what keep the files in run order rather than alphabetical order.

`logs/` is gitignored. The script also prints the last 40 lines of every failing check inline, so
the common case needs no log spelunking at all.

---

## Example output

A full run on this checkout with no stack answering. Note `Builds (0s)` — turbo replayed a cached
build, which is the whole reason phase 3 is one turbo invocation rather than three `next build`
processes:

```
Azmoth — full test suite
  2026-09-09 06:28:36  ·  fc7a518  ·  log: logs/test-all-20260909-062836.log

═══ PHASE 1: Fast Checks ═══

  running: turbo typecheck, turbo lint

  ⤼ SKIP  Python lint — no ruff/black config in the repo
  ✔ PASS  TypeScript typecheck (all packages) (0s)
  ✔ PASS  ESLint (all packages) (0s)

═══ PHASE 2: Engine Tests ═══

  interpreter: apps/engine/.venv/bin/python

  ✔ PASS  Unit tests (pytest tests/) (148s)
  ✔ PASS  Golden suite (tests/test_golden_cases.py) (5s)

═══ PHASE 3: Builds ═══

  running: turbo build (web, marketing, docs — turbo parallelises internally)

  ✔ PASS  Builds (web, marketing, docs) (0s)

═══ PHASE 4: E2E (Partner API) ═══

  ⤼ SKIP  Skipped: stack not running
        probed http://localhost:8000/health and http://localhost:3000
        start one with: make up   (or: pnpm dev, beside uvicorn)

╔══════════════════════════════════════╗
║      AZMOTH TEST SUITE SUMMARY       ║
╠══════════════════════════════════════╣
║ Fast Checks:                 ✅ PASS ║
║ Engine Tests:                ✅ PASS ║
║ Builds:                      ✅ PASS ║
║ E2E:                      ⏭️ SKIPPED ║
╠══════════════════════════════════════╣
║ OVERALL:               ✅ ALL PASSED ║
╚══════════════════════════════════════╝

  153s  ·  logs in logs/test-all-20260909-062836/
```

Exit status `0` — the skipped phase 4 does not fail the run.

And a run with one failing engine test. Phases 3 and 4 are not attempted, the golden suite is
recorded as *not run* rather than silently dropped, and the failure is quoted inline so nothing has
to be looked up:

```
═══ PHASE 2: Engine Tests ═══

  interpreter: apps/engine/.venv/bin/python

  ✘ FAIL  Unit tests (pytest tests/) (149s)
  ⤼ SKIP  Golden suite (tests/test_golden_cases.py) — not run - the unit suite failed first

── Unit tests (pytest tests/) — last 40 lines of logs/test-all-.../1-pytest-unit.log ──
  ................................................................F        [100%]
  =================================== FAILURES ===================================
  ________________ test_temporary_runner_probe_deliberate_failure ________________

      def test_temporary_runner_probe_deliberate_failure():
  >       assert 1 == 2, "deliberate failure, to verify test-all.sh reports it and exits 1"
  E       AssertionError: deliberate failure, to verify test-all.sh reports it and exits 1

  tests/test_zz_temp_runner_probe.py:2: AssertionError
  =========================== short test summary info ============================
  SKIPPED [3] tests/benchmarks/test_performance.py: Skipping benchmark (--benchmark-skip active).
  SKIPPED [4] tests/test_db_persistence.py: POSTGRES_TEST_URL is not set, so the Postgres dialect
  1 failed, 1713 passed, 7 skipped in 147.06s (0:02:27)

╔══════════════════════════════════════╗
║      AZMOTH TEST SUITE SUMMARY       ║
╠══════════════════════════════════════╣
║ Fast Checks:                 ✅ PASS ║
║ Engine Tests:                ❌ FAIL ║
║ Builds:                   -- NOT RUN ║
║ E2E:                      -- NOT RUN ║
╠══════════════════════════════════════╣
║ OVERALL:                   ❌ FAILED ║
╚══════════════════════════════════════╝
```

Exit status `1`. Those seven skips are the expected ones — three benchmarks and four Postgres
dialect tests; see troubleshooting below.

---

## Troubleshooting

**`Python lint — no ruff/black config in the repo`**
Expected, and not a failure. The repository configures no Python linter, and a globally-installed
`ruff` pointed at a repo with no config would lint 40k lines to its own defaults and report
failures nobody agreed to. Add a `pyproject.toml` or `ruff.toml` (root or `apps/engine/`) and the
check turns itself on.

**Phase 2: `no Python interpreter found`**
The script wants `apps/engine/.venv/bin/python`. Create it:

```bash
cd apps/engine
python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

**Phase 2: lots of skips in the log, but a pass**
Read them — `-rs` names the reason for each. Three skips from `tests/benchmarks/` are expected
(`pytest.ini` carries `--benchmark-skip`). More than that usually means the **Soufflé binary is
missing**, and the rules-engine tests are skipping rather than failing: a green run that tested
almost nothing. Install it ([`apps/engine/README.md`](apps/engine/README.md#install)), or run the
suite the way CI does, inside the image:

```bash
docker build -f apps/engine/Dockerfile -t azmoth-engine:local .
docker run --rm -e REQUIRE_ENGINES=1 azmoth-engine:local python -m pytest -rs
```

`REQUIRE_ENGINES=1` turns a missing solver into a failure instead of a skip.

**Phase 2: `POSTGRES_TEST_URL is not set`**
Expected locally. The database tests run against in-memory SQLite unless pointed at a real
Postgres; CI has a job that does exactly that. Nothing to fix.

**Phase 3 dies with no error, or the machine swaps**
`next build` wants roughly a gigabyte per app and turbo runs them concurrently. On a machine with
less than about 4 GB free, the OOM killer arrives and it reads like a build failure:

```bash
TURBO_CONCURRENCY=1 ./scripts/test-all.sh
```

**Phase 3 fails but the log is enormous**
The script prints turbo's own `Failed:` line, which names the app. Then:

```bash
pnpm turbo build --filter=docs      # just the one
```

**Phase 4: `Skipped: stack not running`**
Nothing is answering on `:8000/health` and `:3000`. Start a stack, or accept the skip — it does
not affect the exit code:

```bash
make up                                          # docker compose
docker compose -f infra/docker/docker-compose.dev.yml up --build
```

**Phase 4 fails on sign-in after a previous run**
The E2E script reuses its test account. If a prior run left it on an older password scheme, set
`E2E_LEGACY_PASSWORDS` to that password and it rolls the account forward through
`POST /api/auth/change-password` — see the script's own docstring, which is the authority on this.

**The box borders look ragged**
Your terminal renders `⏭️` as one column instead of two. Cosmetic only; `--no-color` and the log
file are unaffected. The `--` on `NOT RUN` rows is ASCII precisely to avoid this.

**`test-all.sh needs bash 4+`**
macOS ships bash 3.2 as `/bin/bash`. `brew install bash` — the `#!/usr/bin/env bash` shebang picks
up the new one automatically.

---

## What it does *not* cover

Not everything in CI is runnable on a laptop, and the script does not pretend otherwise:

- **Benchmarks** (`pytest tests/benchmarks --benchmark-only`) — they measure wall-clock and are
  meaningless on a machine that is also building three Next.js apps. See
  [`docs/performance_baselines.md`](docs/performance_baselines.md).
- **The Postgres dialect** — needs a real server; CI's `engine-database` job owns it.
- **OpenAPI / contract staleness** — `cd apps/engine && python scripts/export_openapi.py --check`
  then `pnpm generate:contracts`. CI's `contract-and-logic-gate` job owns it.
- **The logic guard and the secret scan** — both need a base ref to diff against, so they are
  pull-request checks by nature.
- **Playwright** (`pnpm --filter web test:e2e`) — browser tests, not wired in here.
