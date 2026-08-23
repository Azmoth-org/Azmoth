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
infra/docker/  compose file for the whole stack: Postgres + engine + web
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
- [`logic/README.md`](logic/README.md) — **read before changing a rule or an objective**
- [`apps/engine/tests/README.md`](apps/engine/tests/README.md) — which tests are golden, which pin
  determinism, which pin the legal posture

## Getting started

### The whole application, one command

```bash
docker compose -f infra/docker/docker-compose.yml up --build
```

That starts three services in order — Postgres, then the engine (which migrates the database with
`alembic upgrade head` before serving), then the web app, each gated on the previous one's
healthcheck:

| | |
| --- | --- |
| <http://localhost:3000> | the UI — Prüfung, Rechnungsprüfung, Stapelprüfung, Regelprüfung |
| <http://localhost:8000/api/v1/health> | the engine's API, and `/docs` for the OpenAPI explorer |

Nothing needs configuring first. `ENGINE_BASE_URL` is set to `http://engine:8000` inside the stack,
and it is deliberately server-side only — the browser never learns the engine's address and talks to
it only through the Next route handlers under `/api/engine/*`.

`docker compose down` stops the stack and keeps the data; `down -v` deletes the
`govatax-postgres-data` volume, which holds approval records — a decision, not a side effect of
stopping. Ports are overridable with `WEB_PORT` and `POSTGRES_PORT`.

### Working on one tier at a time

```bash
# the web app against an engine you are already running
pnpm install && pnpm dev                         # → localhost:3000

# the engine on the host — needs Python 3.11 and the Soufflé 2.5 binary
cd apps/engine
python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/engine_cli.py check     # engines, data, logic, end-to-end probe
.venv/bin/python -m pytest -q                    # 731 tests, against in-memory SQLite
.venv/bin/uvicorn app.main:app --reload
```

See [`apps/engine/README.md`](apps/engine/README.md#install) for the Soufflé install.

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
