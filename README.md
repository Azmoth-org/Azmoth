# wigoo

A monorepo holding a deterministic **GOÄ coding engine** and the Next.js app that will front it.

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
infra/docker/  compose file for the engine
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
approves it.

- [`apps/engine/README.md`](apps/engine/README.md) — install, run, test, Docker, every env var
- [`docs/architecture/ENGINE.md`](docs/architecture/ENGINE.md) — the layers and why each decision is
  made where it is
- [`logic/README.md`](logic/README.md) — **read before changing a rule or an objective**
- [`apps/engine/tests/README.md`](apps/engine/tests/README.md) — which tests are golden, which pin
  determinism, which pin the legal posture

## Getting started

### The web app

```bash
pnpm install
pnpm dev
```

### The engine

Needs Python 3.11 and the Soufflé 2.5 binary. Easiest path is Docker, from the repo root:

```bash
docker compose -f infra/docker/docker-compose.yml up --build engine
curl -s localhost:8000/api/v1/health
```

Or locally — see [`apps/engine/README.md`](apps/engine/README.md#install):

```bash
cd apps/engine
python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/engine_cli.py check     # engines, data, logic, end-to-end probe
.venv/bin/python -m pytest -q                    # 570 tests
.venv/bin/uvicorn app.main:app --reload
```

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
