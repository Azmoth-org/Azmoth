# GOÄ App Stability Audit

**Date:** 2026-08-22 · **Auditor:** read-only automated audit · **Scope:** stability, completeness,
roadmap. No application code, logic, data, tests, migrations, CI or UI was modified.

## 0. What was audited, and a warning about the checkout

> **The working tree is 13 commits behind `origin/main` and does not contain the product.**
>
> `git rev-list --left-right --count HEAD...origin/main` → `0  13`. `HEAD` is `main` at `bbc0eb3`;
> `origin/main` is `ffa4684`. Everything this audit was asked to evaluate exists **only** on
> `origin/main`: `apps/engine/alembic/` (all 3 migrations), `app/db/`, `app/api/rules.py`,
> `app/services/{batch_audit,export,rule_reviews}.py`, `apps/web/app/{padnext,padnext/batch,rules}/`,
> 6 test modules, and `docs/architecture/DATABASE.md` — 57 files in total.
>
> **This report therefore audits `origin/main` (`ffa4684`)**, extracted read-only with
> `git archive origin/main`. Auditing the checked-out tree would have reported "no database, no
> batch audit, no rule review" — all false.
>
> Fix before anything else: `git checkout main && git pull --ff-only` (or work on
> `feat/padnext-batch-audit`). A stale checkout is how a "verified" fix gets re-broken.

Also present in the working tree: an untracked `apps/engine/test.db` (SQLite, 0 proposals,
0 audit_events — no data leak today, but see P0-3).

### Verification actually performed

| Check | Command | Result |
|---|---|---|
| Engine suite | `pytest -rs` (venv, Soufflé 2.5 on PATH) | **715 passed, 5 skipped, 0 failed** (720 collected) |
| Stack self-check | `python scripts/engine_cli.py check` | **18/18 PASS** |
| OpenAPI sync | `python scripts/export_openapi.py --check` | **up to date** — 17 paths, 63 schemas |
| Workspace typecheck | `pnpm typecheck` | **3/3 pass** |
| Workspace lint | `pnpm lint` | **0 errors, 3 warnings** |
| Web build | `pnpm build` | **pass** — 12 routes, Next.js 16.2.6 |
| Compose validity | `docker compose config -q` | **valid**, services: `postgres`, `engine` |
| Image build | `docker compose build` | **pass** — `azmoth-engine:0.3.0`, 264 MB |
| Stack boot | `docker compose up -d` | **pass** — Postgres healthy → engine migrated `<none> → 0003_rule_reviews` → `/health` 200 |
| Lifecycle | live HTTP | solve→`DRAFT`, approve→`APPROVED`, re-approve→**409**, export→200 + attachment, re-export→**409** |
| Audit log | export document | `["CREATED","APPROVED","EXPORTED"]` |
| Rule review | live HTTP | `VERIFIED` written, enforced count 35→36 in the same response |
| Batch audit | live HTTP, bundled synthetic `.padx` | `COMPLETED`; claimed €251.54 = fine €24.25 + wrong €88.49 + unconfirmed €138.80; coverage 44.8 % |
| **Durability** | full `down` + `up`, volume kept | proposal still `EXPORTED`; re-export still 409; batch still `COMPLETED` (€251.54); rule review still applied (36 enforced, 1 review_verified); `migrate --check` = at head |
| Production guard (SQLite) | in-image | **`DatabaseNotDurable` raised** |
| Production guard (auto-create) | in-image | **`SchemaNotMigrated` raised** |
| Dev without Postgres | in-image | **works** on SQLite, `durable=False` |

---

## 1. Executive Summary

**Overall score: 66 / 100**

**Verdict: `needs stabilization` — but narrowly, and not where you feared.**
The engine, the database layer and the contract are production-grade and I verified them running.
What is not finished is the **delivery surface**: the web app is not in the Docker stack, has no
Dockerfile, has no navigation, and its home page is still the unmodified `create-turbo` scaffold.
The app is **ready today for internal rule verification** and **not ready** to be shown to a design
partner without roughly two days of shell work.

### Top 5 strengths (with evidence)

1. **The durability claim is real.** I approved and exported a proposal, tore the whole stack down
   (`docker compose down`, containers removed), brought it back, and the record was still
   `EXPORTED` with its audit chain intact and a second export still refused with 409. Batch results
   and rule reviews survived identically.
2. **The production guards are not decoration.** `APP_ENV=production` + SQLite raises
   `DatabaseNotDurable`; `APP_ENV=production` + `DATABASE_AUTO_CREATE=true` raises
   `SchemaNotMigrated`. Both fire at startup, in the shipped image.
3. **720 tests, all green, and the skips are honest.** The 5 skips are 4 Postgres-dialect
   parametrisations (CI's `engine-database` job runs them against a real Postgres, and greps its own
   output to fail if they skip) plus one repo-hygiene check that needs a git checkout.
   `REQUIRE_ENGINES=1` converts a missing Soufflé from a skip into a failure — the exact trap CI
   was built to avoid.
4. **Zero type drift, structurally.** `openapi.json` is CI-checked against the FastAPI app, and
   `schema.ts` is CI-checked against `openapi.json`. `grep` for `as any`, `: any`, `@ts-ignore`,
   `as unknown as` across `apps/web` returns **nothing**.
5. **The audit log is append-only in code, not in a comment.** SQLAlchemy `before_update` /
   `before_delete` listeners on `AuditEvent` raise `AuditLogIsAppendOnly`. Every decision writes its
   audit row in the *same transaction* as the status change, behind `SELECT … FOR UPDATE`.

### Top 5 gaps

1. **`docker compose up --build` does not start the app.** It starts Postgres and the engine. There
   is no `apps/web/Dockerfile` and no `web` service. The frontend has no deployment story at all.
2. **The home page is scaffold.** `apps/web/app/page.tsx` renders *"Project ready! You may now add
   components and start building."* with a demo Button. That is the first screen anyone sees.
3. **No navigation, and no way back to a stored record.** The 4 real screens do not link to each
   other. There is no proposal list and no batch lookup in the UI, so a durable record becomes
   unreachable the moment the browser reloads — even though `GET /api/v1/proposals` exists.
4. **Documentation has drifted behind the product.** 4 files claim "649 tests" (actual: 720). The
   engine README's endpoint table lists 12 of 17 routes — the entire batch path and all three rule
   endpoints are missing. README and CONTRIBUTING still describe the web app as "the review UI at
   `/review`", 3 screens ago.
5. **A stranded batch has no operator recovery.** `BackgroundTasks` is not durable (documented
   honestly in 3 places), a restart mid-batch leaves `batch_jobs.status = PROCESSING` forever, and
   there is no reaper, no `--stale` CLI, and no way to list stuck jobs.

### Biggest risk

**Not the engine — the gap between how trustworthy the engine is and how unfinished the app looks.**
The compliance argument in this repository is genuinely strong: three-bucket honesty, receipt
hashes, an append-only log, a refusal to start on a non-durable database. A design partner will
form their judgement from a scaffold home page with no navigation, and will never see any of it.
The second-order risk is the stale checkout: work is being verified against a tree that does not
contain the feature.

---

## 2. Full App Runbook

### Current status

**The engine stack works, verified end to end. The web app is not part of it.**

```bash
# Verified working — Postgres + engine, migrated automatically:
docker compose -f infra/docker/docker-compose.yml up --build
curl -s localhost:8000/api/v1/health          # → 200, status "ok", souffle_available true
```

Observed boot sequence: `postgres` healthy (`pg_isready` against the real user/db) → engine
entrypoint runs `migrate.py --wait 60` → `<none> → 0001_proposals_audit → 0002_batch_audit →
0003_rule_reviews` → `uvicorn` → `Application startup complete`.

The web app must be started separately, on the host:

```bash
pnpm install
pnpm dev                                       # → localhost:3000, talks to ENGINE_BASE_URL
```

**There is no single command that starts the full app.**

### Answers to the specific questions

| Question | Answer |
|---|---|
| Exact command for the full app | **Does not exist.** Two commands, one of which is not containerised. |
| Engine migrations run automatically | **Yes** — `ENTRYPOINT ["/srv/scripts/docker-entrypoint.sh"]`, so they run whatever `command:` compose supplies. Verified in the boot log. |
| Web has env vars for the engine URL | **Yes, but only for host dev.** `apps/web/.env.example` documents `ENGINE_BASE_URL`; it is correctly server-only (not `NEXT_PUBLIC_`), and `turbo.json` passes it through. Nothing sets it for a container, because there is no container. |
| Postgres data persists | **Yes** — named volume `azmoth-postgres-data`, deliberately not a bind mount. Verified: survived a full `down`/`up`; `down -v` is the only way to remove it. |
| Development only, or production-like | **Development only.** Compose forces `--reload`, bind-mounts `app/`, `logic/`, `data/`, `alembic/` read-only, and defaults `APP_ENV=development`. The *image* is production-capable (`APP_ENV=production`, `DATABASE_AUTO_CREATE=false`, non-root uid 10001, no `DATABASE_URL` default so it fails loudly). There is no production compose file or override. |
| Healthcheck endpoints | **Yes, and a good one** — the healthcheck asserts `souffle_available && status=="ok"`, not merely that the port is open. Postgres has `pg_isready`; `engine` waits on `service_healthy`. |
| Web proxy to engine | **Yes, and well designed** — 11 route handlers under `/api/engine/*`. The browser never learns the engine's address; every failure mode (timeout, empty body, unparsable JSON) is normalised into a renderable German error. This is the seam authentication will eventually sit in. |

### Recommended fix

Add `apps/web/Dockerfile` (standalone Next output) and a `web` service to the existing compose file
with `ENGINE_BASE_URL=http://engine:8000` and `depends_on: engine: service_healthy`. See §8 for the
exact shape. Nothing else in Area 1 needs to change.

---

## 3. Area Scores

| Area | Score /10 | Status | Main Gap |
|---|---:|---|---|
| Full app runnability | 5 | Partial | No web Dockerfile, no `web` service — `compose up` starts 2 of 3 tiers |
| Engine stability | 8 | Strong | Stranded `PROCESSING` batches have no reaper; `/health` cannot see the DB |
| Database stability | 8 | Strong | No backup/restore runbook; `REVOKE UPDATE, DELETE` documented but never applied |
| UI professionalism | 5 | Unfinished shell, strong screens | Scaffold home page, no navigation, no route back to a stored record |
| Contracts / type safety | 9 | Excellent | Nothing material — `lint` does not run in the contracts package |
| CI / release safety | 7 | Strong | No web image build; logic guard is PR-only and satisfiable by touching any golden file |
| Documentation | 6 | Good but drifted | Stale test counts (4 files), 5 undocumented endpoints, 3 undocumented screens, no full-app runbook |
| Pilot readiness | 5 | Conditional | Rule verification ready now; demo needs a shell; real data legally blocked |

---

## 4. Critical Missing Pieces (P0 — before rule verification or a pilot)

**P0-1 · The checkout is 13 commits behind `origin/main`.**
The working tree has no `alembic/`, no `app/db/`, no batch audit, no rule review, no `/padnext`,
no `/rules`. Any verification run against it is meaningless. *Fix:* `git pull --ff-only` on `main`.
Cost: one command.

**P0-2 · `docker compose up --build` does not start the web app.**
No `apps/web/Dockerfile` exists; the compose file has exactly two services (`docker compose config
--services` → `postgres`, `engine`). Every reviewer, design partner and pilot user needs two
different toolchains (Docker *and* pnpm/Node 22) and a manual `ENGINE_BASE_URL`. *Fix:* §8.
Cost: ~half a day.

**P0-3 · `.gitignore` has no `*.db` / `*.sqlite` rule, so an approval database can be committed.**
`git check-ignore apps/engine/test.db` exits 1 — it is **not** ignored. The engine's own
`DATABASE_URL` default is `sqlite+aiosqlite:///./test.db`, so any developer who runs `uvicorn`
locally and approves a proposal creates an untracked SQLite file holding approval records that
`git add -A` would commit. `.dockerignore` already excludes `**/test.db`, `**/*.sqlite*` and
`apps/engine/*.db`; `.gitignore` was never given the same lines, and CI's secret scan only looks for
`.env` files and credential-shaped strings, so it would not catch it. *Fix:* copy the three
patterns from `.dockerignore` into `.gitignore`. Cost: one line. **This is the cheapest P0 in the
list and the only one with a data-hygiene consequence.**

**P0-4 · The home page is the unmodified scaffold.**
`apps/web/app/page.tsx` — *"Project ready! You may now add components and start building."*
No product exists at `/`. The four real screens are reachable only by typing their URLs. *Fix:*
replace with an index of the four screens (§7). Cost: ~2 hours.

**P0-5 · A stranded batch cannot be found or cleared by an operator.**
`process_batch` runs in a FastAPI `BackgroundTask`; a restart mid-batch leaves `batch_jobs.status =
PROCESSING` with files still `PENDING`. The limitation is documented honestly in `batch_audit.py`,
`DATABASE.md` and the UI (the browser stops polling after `POLL_TIMEOUT_MS` and explains why in
German — genuinely good). What is missing is the operator half: no reaper on startup, no
`GET /padnext/batch` list endpoint, no CLI. `grep -rn "reap\|orphan\|stranded\|stale"` over
`apps/engine/app/` finds only docstrings. *Fix:* a startup pass that marks pre-existing `PROCESSING`
jobs `FAILED` with `error_message="interrupted by a restart"`. Cost: ~2 hours, no new dependency.
**Do this before rule verification** — a reviewer who strands a 100-file batch has no way to tell.

---

## 5. Important But Not Blocking (P1)

**P1-1 · No route from the UI back to a stored record.** `GET /api/v1/proposals` (list, filterable
by status) exists in the engine and is exposed in `ENGINE_ROUTES`, but there is no
`/api/engine/proposals` list route handler and no page. `batchId` lives in React state only, so a
page reload orphans a completed batch permanently from the user's point of view. The whole argument
for Postgres was durability; the UI cannot reach it.

**P1-2 · `/health` cannot detect database loss.** `HealthResponse` deliberately omits the database
(to keep the OpenAPI document frozen — a defensible call, stated in `config.py`). Consequence: a DB
that dies *after* startup leaves the container reporting `status: "ok"` and the Docker healthcheck
green, while every approval 500s. Needs either a new field (a deliberate contract change) or a
separate `/readyz`.

**P1-3 · No backup, restore or retention procedure.** `DATABASE.md` is 518 excellent lines on
schema, migrations and testing, and contains no `pg_dump`, no restore, no retention. For a table
whose purpose is to be shown to a Rechnungsprüfer, "we have a named volume" is not a backup story.

**P1-4 · `REVOKE UPDATE, DELETE ON audit_events` is documented in three places and applied in
none.** Append-only is enforced in the ORM only. A raw `UPDATE` from a psql session, or any future
service method that bypasses the mapper, rewrites the log. The migration explains *why* it is out of
scope (Alembic runs as owner and cannot know the app role's name) — that reasoning is sound, but the
grant then needs to exist somewhere, and it does not.

**P1-5 · Rule reviews are refreshed per worker process.** `refresh_pipeline_rules` rebuilds the
pipeline's store in the process that served the write. Under `--workers > 1`, a rule verified on
worker A is live there and on worker B only after a restart. Honestly documented; the failure mode
is a rule enforced later than the dashboard claims, never a wrong answer. It becomes a real problem
the moment you scale past one worker.

**P1-6 · Zero frontend tests.** No `*.test.*`, no `*.spec.*`, no vitest/jest/playwright config
anywhere in `apps/web` or `packages/`. The approval and export flows — the legally load-bearing
interactions — are covered only by `tsc` and a Next build. One Playwright smoke test over
solve→approve→export would be worth more than any UI polish in §6.

**P1-7 · No `error.tsx`, `not-found.tsx` or `loading.tsx` anywhere in `apps/web/app`.** An
unhandled render error in a client component shows the Next.js default error page. In-component
error handling is otherwise good (`ErrorPanel`, per-flow German messages), so this is a missing
outer boundary, not missing care.

**P1-8 · CI does not build the web image and does not validate compose.** `web-checks` runs
lint/typecheck/build/contract-sync; nothing builds a deployable web artefact (there is none) and
nothing runs `docker compose config`. A compose file broken by an edit would ship green.

**P1-9 · The secret scan is a narrow regex.** It catches `sk-…`, `AKIA…`, PEM headers and tracked
`.env` files. It would not catch a Postgres URL with a real password, a JWT, a GCP service-account
JSON or a Slack token. No `gitleaks`/`trufflehog`, and no dependency-vulnerability job at all.

**P1-10 · The logic guard is weaker than it reads.** It is correctly described in its own comments
as refusing "the case where nobody looked", and it is genuinely valuable. Two real limits:
`if: github.event_name == 'pull_request'` means a direct push to `main` bypasses it entirely (so it
depends on branch protection that this repository cannot prove is enabled), and the evidence test is
`git diff --name-only | grep '^logic/tests/(golden|cases)/'` — a whitespace change to any golden
file satisfies it.

---

## 6. Polish / Professionalism (P2)

1. **`<html lang="en">`** in `apps/web/app/layout.tsx` while 100 % of the UI copy is German. Screen
   readers will pronounce "Abrechnungsvorschlag" with English phonemes.
2. **No `metadata` on the root layout**, so `/` has whatever title Next infers. The four real pages
   each set a good German `title` + `description` — only the shell was skipped.
3. **Unused `Geist` import** in `layout.tsx` (`Geist`, `Geist_Mono`, `Inter` imported; `Geist` never
   used). ESLint does not flag unused imports, which is itself worth fixing.
4. **The dark-mode toggle is an undiscoverable global hotkey.** `ThemeHotkey` listens for any
   bare `d` keypress outside an input and flips the theme. There is no visible control anywhere.
   Pressing `d` while scanning a positions table silently changes the theme — a scaffold leftover
   whose only documentation is the scaffold home page this audit is asking you to delete.
5. **Receipt hashes cannot be copied.** `grep -rn clipboard apps/web` → nothing. `ProposalHeader`
   truncates `receipt_hash` to 24 chars with the full value in a `title` tooltip. The receipt hash
   *is* the evidence; a reviewer needs to paste it into a ticket.
6. **The page shell is copy-pasted four times.** `<main className="mx-auto w-full max-w-7xl
   space-y-6 px-4 py-8 sm:px-6">` appears verbatim in all four pages, each re-declaring its own
   `<header>`. One `<AppShell>` would remove the drift risk entirely.
7. **Accessibility is inconsistent across generations.** `components/padnext/*` and
   `components/rules/*` use `aria-*` / `role=` throughout; **none** of the nine
   `components/review/*` files do. The older screen is the one with the approval buttons.
8. **Loading affordances are inconsistent.** `padnext/*` and `rules/*` use `Loader2Icon
   animate-spin`; the review screen signals pending state through disabled buttons and text only.
9. **3 ESLint warnings**, all `react-hooks/set-state-in-effect` in the newest code
   (`components/rules/review-dialog.tsx:62`, `components/rules/review-workbench.tsx:72`). Warnings,
   not errors — but they are the only lint output in the repo, so they will be ignored forever or
   fixed in ten minutes.
10. **No breadcrumbs and no cross-links** beyond two contextual inline links (`/rules` → `/padnext`,
    `/padnext/batch` → `/padnext`). `/review` links nowhere.

**Explicitly good, do not "fix":** the German copy is excellent and consistent (no English leakage in
user-facing strings); `SyntheticDataBanner` states all three required disclaimers on every load of
every data screen; its absence on `/rules` is deliberate and justified in a code comment; raw JSON
appears only inside a bounded `RawJson` panel behind a technical-details affordance, never dumped
into a page; empty states are written as *explanations* rather than "No data"; the batch
`FAILED` state explicitly refuses to show a roll-up and says why; the three-bucket presentation is
protected by prose in the UI, the schema and the contract from ever being summed into one
"at risk" figure. That last one is the most valuable thing in the frontend.

---

## 7. UI Improvement Plan

Not a redesign. The four screens are good; the container around them is missing. Roughly
2–3 days total, in this order.

**1 · App shell** (~4 h) — one `components/layout/app-shell.tsx`: fixed top bar (product name +
environment badge reading `app_env` from `/health`, so "DEVELOPMENT" is visible at all times),
persistent left sidebar, `<main>` slot carrying the `max-w-7xl px-4 py-8` that is currently
copy-pasted four times. Mount it in `layout.tsx`. Delete the four duplicated wrappers.

**2 · Navigation** (~1 h) — four sidebar entries, active state from `usePathname()`:
Prüfung (`/review`) · Rechnungsprüfung (`/padnext`) · Stapelprüfung (`/padnext/batch`) ·
Regelprüfung (`/rules`). Group the last one under a "Intern" heading — it is a different job.

**3 · Home page** (~2 h) — replace the scaffold. Four cards, one per screen, each with the
one-sentence description already written in that page's `metadata.description`, plus a live
coverage line from `GET /api/v1/rules/coverage` ("36 von 894 Regeln verifiziert") and the catalog
version from `/health`. This single change does more for perceived credibility than everything else
in this section.

**4 · Page headers** (~2 h) — a `<PageHeader title description>` component. Keep every existing
German paragraph verbatim; they are the best copy in the project. Add a breadcrumb only on
`/padnext/batch` (Rechnungsprüfung › Stapel), where there is a real hierarchy.

**5 · Warning banners** (~1 h) — no content change. Move `SyntheticDataBanner` into the shell so it
cannot be forgotten on a future screen, with an explicit opt-out prop for `/rules` (whose exemption
is already reasoned in a comment). Add a persistent "Entwurf — keine Rechnung" chip beside the
status badge in `ProposalHeader`.

**6 · Table design** (~3 h) — the tables are already readable and correctly `tabular-nums`. Two
additions: sticky headers (a 100-file batch table scrolls past its own header), and `aria-sort` /
`scope="col"` in `components/review/*` to match what `padnext/*` already does.

**7 · Empty / loading / error states** (~3 h) — add `app/error.tsx`, `app/not-found.tsx` and one
`app/loading.tsx`. Standardise on the `Loader2Icon animate-spin` pattern the newer components
already use, and apply it to the review screen. Empty-state *copy* needs no work.

**8 · Export / approval dialogs** (~2 h) — `decision-dialogs.tsx` already collects a name and
explains the transition. Two gaps: no explicit "this is irreversible" line on export (it is
terminal, and the code knows it), and no confirmation of the resulting audit event. Add both as one
sentence each.

**9 · Trust indicators** (~3 h) — a `<CopyableHash>` component (mono, truncated, click-to-copy with
a confirmation) used for `receipt_hash`, `input_hash`, `proposal_id`, `batch_id` and
`catalog_sha256`. Add a visible theme toggle in the shell and **delete the bare-`d` hotkey**.

**10 · German wording** (~1 h) — set `lang="de"`, add root `metadata`, remove the unused `Geist`
import, and fix the 3 ESLint warnings. Mechanical, and it stops a reviewer's first impression being
a browser tab that says the wrong thing.

**Deliberately not proposed:** no component library change, no restyling of the four workbenches,
no new charts, no route restructuring.

---

## 8. Docker / Deployment Gap Plan

### `apps/web/Dockerfile` — **missing, must be created**

Multi-stage, `pnpm` + `output: "standalone"` (requires adding that to `next.config.ts`, which
currently sets only `transpilePackages`). Build context must be the **repo root**, exactly like the
engine's, because the app depends on the `@workspace/ui` and `@workspace/contracts` workspace
packages. Copy `pnpm-lock.yaml`, `pnpm-workspace.yaml` and the `packages/*` manifests before the
source so the install layer caches. Run as a non-root uid, mirroring the engine's `10001` pattern.
`EXPOSE 3000`, `CMD ["node", "server.js"]`.

### `infra/docker/docker-compose.yml` — **incomplete, needs a third service**

The existing two services are well built (healthchecks, named volume, `service_healthy` gating,
locale-pinned initdb, read-only source mounts, per-setting comments explaining the *why*). Add:

```yaml
  web:
    build:
      context: ../..
      dockerfile: apps/web/Dockerfile
    image: azmoth-web:0.3.0
    depends_on:
      engine:
        condition: service_healthy
    ports:
      - "${WEB_PORT:-3000}:3000"
    environment:
      # Server-side only, deliberately not NEXT_PUBLIC_: the browser must never learn the
      # engine's address. `engine` is the compose service name on the default network.
      ENGINE_BASE_URL: "http://engine:8000"
      NODE_ENV: "production"
    healthcheck:
      test: ["CMD", "node", "-e", "fetch('http://localhost:3000/').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"]
      interval: 30s
      timeout: 10s
      start_period: 20s
      retries: 3
    restart: unless-stopped
```

### `.env.example` files — **present and good, one addition**

`apps/engine/.env.example` (113 lines, every setting documented, asserted by
`tests/test_production_fixes.py`) and `apps/web/.env.example` both exist. Add `WEB_PORT` and
`POSTGRES_PORT` to a new root `.env.example` documenting the compose-level knobs
(`APP_ENV`, `POSTGRES_USER/PASSWORD/DB/PORT`, `DATABASE_URL`, `MIGRATION_WAIT_SECONDS`), which are
referenced by the compose file but documented nowhere.

### Healthchecks — **present, one gap**

Postgres (`pg_isready` against the real user/db, not the defaults) and engine (asserts
`souffle_available && status=="ok"`, not just that the port answers) are both better than typical.
Add the `web` one above. Separately, `/health` should be able to report database reachability
(P1-2) so the engine's healthcheck can fail when Postgres dies after startup.

### Migration entrypoint — **already correct, no change**

`ENTRYPOINT ["/srv/scripts/docker-entrypoint.sh"]` + `migrate.py --wait 60`, with `RUN_MIGRATIONS`
and an explicit no-`DATABASE_URL` branch. Verified applying all three revisions from scratch. The
reasoning for entrypoint-over-chained-CMD (compose overrides `command:` to add `--reload`) is
correct and worth preserving.

### Also missing

- **A production-like compose profile.** The current file is development-shaped (`--reload`, source
  bind mounts, `APP_ENV=development`). Add `docker-compose.prod.yml` as an override that drops the
  mounts and `--reload` and sets `APP_ENV=production` — which then exercises the two startup guards
  this audit verified.
- **A one-command entry point.** Add `"stack": "docker compose -f infra/docker/docker-compose.yml up
  --build"` to the root `package.json` scripts so there is one documented answer to "how do I run
  this".

---

## 9. Stability Checklist

- [ ] **full app starts with one command** — engine + Postgres yes (verified); **web is not in the stack**
- [x] **engine tests pass** — 715 passed, 5 skipped, 0 failed (720 collected); `engine_cli check` 18/18
- [x] **web build passes** — `pnpm build` green, 12 routes; typecheck 3/3; lint 0 errors / 3 warnings
- [x] **contracts in sync** — `export_openapi.py --check` "up to date" (17 paths, 63 schemas); both halves CI-gated
- [x] **database migrations work** — `<none> → 0003_rule_reviews` applied live; `--check` idempotent; models-vs-migration drift test in the suite
- [x] **proposals persist after restart** — verified `EXPORTED` + `approved_by` survived a full `down`/`up`
- [x] **audit events persist after restart** — verified: re-export still 409; export document carries `CREATED, APPROVED, EXPORTED`
- [x] **rule reviews persist after restart** — verified: 36 enforced, `review_verified_rule_count: 1`
- [ ] **batch jobs survive or fail clearly** — they **fail clearly to the browser** (poll timeout + an explicit German explanation) but a stranded row stays `PROCESSING` forever with no reaper and no list endpoint
- [ ] **UI has no broken states** — no scaffold-free home page, no navigation, no `error.tsx`/`not-found.tsx`, no route back to a stored record
- [x] **export works** — proposal export verified (attachment + correct filename + 409 on re-export); batch CSV/ZIP export path present and idempotent by design
- [x] **no secrets committed** — no tracked `.env`; only compose-default dev credentials (`azmoth`/`azmoth`); a test fails if a settings field named `*key*`/`*secret*`/`*token*`/`*password*`/`*credential*` appears
- [x] **no PHI committed** — synthetic fixtures only, each self-declaring; `data/licensed/` gitignored except its README with a test asserting it; PADnext models parse no identity field; `echtdaten="1"` refused with 422
- [x] **CI protects logic/data changes** — the logic guard does gate `logic/asp`, `logic/datalog`, `data/catalogs`, `data/rules` on golden-snapshot evidence, **with two caveats**: PR-only (a direct push to `main` bypasses it) and satisfied by touching any file under `logic/tests/`

---

## 10. Recommended Next Actions

1. **`git pull --ff-only` on `main`.** Everything below is invisible until the checkout matches
   `origin/main`. One command. *(P0-1)*
2. **Add the three `*.db` / `*.sqlite` patterns from `.dockerignore` to `.gitignore`.** One line,
   closes the only data-hygiene hole in the repository. *(P0-3)*
3. **Add `apps/web/Dockerfile` + the `web` service in §8**, so `docker compose up --build` starts
   the whole product. Half a day, and it unblocks every kind of demo. *(P0-2)*
4. **Mark pre-existing `PROCESSING` batches `FAILED` at startup, and add `GET /api/v1/padnext/batch`
   (list).** Two hours, no new dependency, and it removes the one silent failure mode a rule
   reviewer can hit. *(P0-5)*
5. **Do steps 1–3 of the §7 plan — app shell, navigation, real home page.** ~7 hours. This is the
   whole difference between "an impressive engine behind a scaffold" and "a credible internal
   compliance tool". *(P0-4)*

Stop there. Do not start the real-data pilot work in §11 and do not add features — items 1, 2 and 4
are cheap correctness fixes, and 3 and 5 are the only things standing between this engine and a
demo that does it justice.

---

## 11. Pilot Readiness (Area 8 detail)

### Internal rule verification — **READY**

The workflow exists end to end and I exercised it live: `GET /rules/review-queue` returned a
backlog of **859** with the full GOÄ sentence attached per rule (never truncated — the quote is the
evidence a reviewer decides on), `POST /rules/{id}/review` recorded `VERIFIED` and re-merged the
running engine in the same response, enforced count moved 35 → 36, and the decision survived a
restart. The CSVs are never written — decisions are an overlay in `rule_reviews`, merged at load
time — so `data/rules/` keeps needing a reviewed PR with a second approver, which is exactly right.
`effective_rules_hash` correctly folds decided reviews into the receipt hash and cache key, and
returns the CSV digest **byte-identically** when nothing is decided, so every existing golden
receipt stays valid.

*Blockers:* none.
*Minimum fixes first:* P0-1 (pull), P0-5 (batch reaper — a reviewer will use the batch screen to
see the effect of their verifications and needs to know when a run stranded).

### Synthetic mock pilot — **CONDITIONALLY READY**

Engine, database, contract and the four screens all work. What a pilot user hits: a scaffold home
page, no navigation, and no way to find yesterday's proposal.
*Blockers:* P0-2, P0-4, P1-1.
*Minimum fixes:* §7 steps 1–3 plus a proposals list page (~1.5 days total).

### Design-partner demo — **CONDITIONALLY READY**

The substance is genuinely strong and demo-worthy: three-bucket honesty, receipt hashes, proof
trees, an append-only log, `unconfirmed` explained as *our* coverage limit rather than an accusation.
Presenting it through a `create-turbo` placeholder actively undermines it.
*Blockers:* P0-2, P0-4, plus §7 steps 1–4 and 9 (copyable hashes — a partner will ask "can I keep
that hash?").
*Minimum fixes:* ~2–3 days. Add one Playwright smoke test over solve→approve→export (P1-6) before
demoing live; a UI regression during a demo costs more than the test.

### Real data pilot — **BLOCKED. Legal, not engineering.**

`docs/compliance/PRIVATE_DATA_WARNING.md` (111 lines) enumerates this honestly and I found no
contradiction between what it claims and what the code does. Outstanding and **not** closeable by
writing code: no access control (every endpoint answers unauthenticated; `approved_by`,
`reviewed_by` and `exported_by` are self-asserted strings, and the audit log records reads as
`anonymous`), no encryption at rest or in transit, no retention or erasure mechanism, no § 203 StGB
workflow, no AVV, no DPIA (health data is Art. 9 special-category — a DPIA is not optional), no
EU-hosting guarantee, no backup/DR/breach process, no pen test.

The guards that do exist are safety rails and are correctly labelled as such: `echtdaten="1"`
refused with 422, no patient identity parsed anywhere, `data/licensed/` gitignored with a test,
no credential-shaped settings field permitted.

*Blocker:* a legal determination that must happen before the first real record, plus authentication
as the first engineering prerequisite. The `/api/engine/*` proxy layer is already the correct seam
for it.
*Do not schedule this alongside the items in §10.*
