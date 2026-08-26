# Govatax

A monorepo holding a deterministic **GOÄ coding engine** and the Next.js app that fronts it.

```
apps/
  engine/      Python 3.11 FastAPI — the coding engine and the PADnext auditor
  web/         Next.js 16 + shadcn/ui
packages/
  contracts/   generated API contract shared by both (OpenAPI → TypeScript)
  ui/          shadcn/ui components
  eslint-config/, typescript-config/
logic/         the symbolic layer: Clingo ASP + Soufflé Datalog + golden cases
data/          the GOÄ catalog, rule tables and mappings, with provenance
docs/          architecture, compliance, migration
infra/docker/  compose files for the whole stack: Postgres + engine + web, prod base + dev overlay
```

> ⚠️ **Synthetic data only.** The engine implements no access control, no audit logging and no PHI
> handling. Read [`docs/compliance/PRIVATE_DATA_WARNING.md`](docs/compliance/PRIVATE_DATA_WARNING.md)
> before pointing anything real at it.

## The engine

GOÄ (the German fee schedule for private medical billing) coding where the legal reasoning is
symbolic and auditable: a CSV bridge proposes candidate positions, a Soufflé Datalog program decides
what is certainly chargeable, a Clingo ASP program resolves what genuinely requires a choice under a
hard timeout, an independent validation pass re-checks the result, and every line carries a proof
tree with rule ids and paragraph references. No model runs anywhere in it.

The output is a **DRAFT proposal**, not an invoice. It leaves `DRAFT` only when a named person
approves it — and that approval is durable: proposals live in Postgres, every decision writes a row
in an append-only audit log, and re-deciding a decided proposal is refused with HTTP 409.

- [`apps/engine/README.md`](apps/engine/README.md) — install, run, test, Docker, every env var
- [`docs/architecture/ENGINE.md`](docs/architecture/ENGINE.md) — the layers and why each decision is
  made where it is
- [`docs/architecture/DATABASE.md`](docs/architecture/DATABASE.md) — the two tables, the audit log,
  and how to run migrations
- [`docs/errors.md`](docs/errors.md) — every `error_code` the API can return, what triggers it and
  what a client should do about it
- [`docs/performance_baseline.md`](docs/performance_baseline.md) — where a solve actually spends its
  time, and what counts as slow
- [`docs/performance_baselines.md`](docs/performance_baselines.md) — the baselines and soft/hard
  thresholds `tests/benchmarks/` gates against, and the machine they were measured on
- [`logic/README.md`](logic/README.md) — **read before changing a rule or an objective**
- [`apps/engine/tests/README.md`](apps/engine/tests/README.md) — which tests are golden, which pin
  determinism, which pin the legal posture

## Getting started

### The whole application, one command

For local development — both `engine` (`uvicorn --reload`) and `web` (`next dev`) run against the
working tree, bind-mounted in, so editing code is a save, not a rebuild:

```bash
docker compose -f infra/docker/docker-compose.dev.yml up --build
```

`--build` is only needed again after a dependency changes (`requirements.txt`, `package.json`, the
lockfile) or a Dockerfile itself changes — not for application code.

For a production-parity smoke test — the standalone Next.js build and the engine image exactly as
they'd ship, no bind mounts, no reload — use the other file instead:

```bash
docker compose -f infra/docker/docker-compose.yml up --build
```

These are two independent, standalone files (not a base + override — pass one `-f`, not both), so
either one to run alone with whatever tooling you use, an IDE task included. They share one local
Postgres volume, so switching between them keeps your data; just don't run both at once, since their
container names collide.

Either way it starts four services in order — Postgres, then the engine (which migrates the
proposals and the audit log with `alembic upgrade head` before serving) and a one-shot that creates
Better Auth's tables in the same database, then the web app, each gated on the previous one:

| | |
| --- | --- |
| <http://localhost:3000> | the UI — Prüfung, Rechnungsprüfung, Stapelprüfung, Regelprüfung |
| <http://localhost:8000/api/v1/health> | the engine's API, and `/docs` for the OpenAPI explorer |

Nothing needs configuring first for the dev stack. `ENGINE_BASE_URL` is set to
`http://engine:8000` inside it, and it is deliberately server-side only — the browser never learns
the engine's address and talks to it only through the Next route handlers under `/api/engine/*`.

**Every screen is behind a login.** Open <http://localhost:3000>, get sent to `/login`, and use
*Registrieren* once to create an account; the session cookie then carries you, and the user id
behind it is written into the audit log for everything you do (`audit_events.actor`,
`proposals.created_by`). Sign-up is open — that is fine for a build holding only synthetic data and
is one of the gaps [`docs/compliance/PRIVATE_DATA_WARNING.md`](docs/compliance/PRIVATE_DATA_WARNING.md)
tracks.

**Google sign-in is optional and off.** Set `GOOGLE_CLIENT_ID` *and* `GOOGLE_CLIENT_SECRET` and a
*Mit Google anmelden* button appears on both auth screens; leave them unset and the provider is
never registered and no button is rendered. Register
`http://localhost:3000/api/auth/callback/google` under *Authorised redirect URIs* on the OAuth
client — Google matches it character for character — and read the section in
[`apps/web/.env.example`](apps/web/.env.example) first: it is a redirect to a third party that then
knows who signed in to this deployment and when, which is a decision to make per deployment rather
than a default. Note that an account created here with a password cannot then sign in with Google at
the same address; Better Auth will not link the two while the local address is unverified, and with
no mail transport configured none of them is.

The production-parity stack needs one thing set, and refuses to start without it rather than
defaulting: `BETTER_AUTH_SECRET`, which signs the session cookies. A value that changes between
boots signs sessions the next container cannot verify.

```bash
BETTER_AUTH_SECRET=$(openssl rand -base64 32) \
  docker compose -f infra/docker/docker-compose.yml up --build
```

`docker compose down` stops the stack and keeps the data; `down -v` deletes the
`govatax-postgres-data` volume, which holds approval records — a decision, not a side effect of
stopping. Ports are overridable with `WEB_PORT` and `POSTGRES_PORT`.

Keep the `--build`, and after a pull that adds a dependency add `--renew-anon-volumes` too:

```bash
docker compose -f infra/docker/docker-compose.dev.yml up --build --renew-anon-volumes
```

Both services bind-mount the working tree, so a plain `up` runs current code inside whatever was
installed the last time their packages were built — and after a pull that adds a dependency, that
install no longer has it. The two need different flags to fix, which is the whole reason this
paragraph exists. The engine keeps its packages in an image layer, so `--build` refreshes them. The
web app's `node_modules` is an **anonymous volume**, which compose *keeps* when it recreates a
container: a fresh image gets the same stale volume mounted back over it, and `--build` alone
changes nothing. `--renew-anon-volumes` replaces it. Named volumes are untouched by that flag, so
the Postgres data survives it.

Both containers check for this on start and stop with the missing package names and the right
command rather than failing obscurely — the engine would otherwise crash-loop on an import, and the
web app would answer 404 to every request while reporting itself `Up (unhealthy)`.
`CHECK_DEPS=false` skips either check.

### Working on one tier at a time

```bash
# the web app against an engine you are already running
pnpm install                                     # → localhost:3000
pnpm --filter web auth:migrate                   # once: Better Auth's user/session/account tables
pnpm dev

# the engine on the host — needs Python 3.11 and the Soufflé 2.5 binary
cd apps/engine
python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/engine_cli.py check     # engines, data, logic, end-to-end probe
.venv/bin/python -m pytest -q                    # 731 tests, against in-memory SQLite
.venv/bin/uvicorn app.main:app --reload
```

See [`apps/engine/README.md`](apps/engine/README.md#install) for the Soufflé install.

`auth:migrate` is idempotent and needs running only when Better Auth's schema changes. With nothing
configured it targets the same SQLite file the engine defaults to (`apps/engine/test.db`), so the
accounts and the proposals stay in one database — which is the point, since an audit row's actor is
a `user.id` that has to resolve by a join. Set `AUTH_DATABASE_URL` to point both at Postgres; the
engine's SQLAlchemy spelling (`postgresql+asyncpg://…`) is accepted and normalised, so one value can
be shared verbatim. `--dry` prints the SQL and changes nothing.

## Shared types

The front end never transcribes a schema by hand. The engine exports its OpenAPI document and
`openapi-typescript` generates the TypeScript from it:

```bash
cd apps/engine && .venv/bin/python scripts/export_openapi.py   # → packages/contracts/openapi/
pnpm generate:contracts                                        # → packages/contracts/typescript/
```

```tsx
import type { Proposal, SolveRequest } from "@workspace/contracts";
```

See [`packages/contracts/README.md`](packages/contracts/README.md) for why this exists and what a
generated type does and does not prove.

## UI components

To add components to the web app, run this at the repo root:

```bash
pnpm dlx shadcn@latest add button -c apps/web
```

They land in `packages/ui/src/components` and are imported from the `ui` package:

```tsx
import { Button } from "@workspace/ui/components/button";
```
