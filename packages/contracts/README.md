# `@workspace/contracts`

The single definition of what `apps/engine` and `apps/web` say to each other.

```
openapi/openapi.json     exported from the FastAPI app — the source of truth
typescript/schema.ts     generated from it by openapi-typescript — DO NOT EDIT
typescript/index.ts      hand-written, tiny: named aliases for the types a client actually uses
```

## Regenerating

Two steps, in this order. Neither needs a running engine.

```bash
# 1. Python → OpenAPI  (from apps/engine, with its venv active)
python scripts/export_openapi.py

# 2. OpenAPI → TypeScript
pnpm --filter @workspace/contracts generate
```

Commit both outputs. They are reviewed artefacts, not build products: a schema change should be
visible in a pull request, and `apps/web` must build without an engine on the machine.

CI check — fails if `openapi.json` no longer matches the app:

```bash
python scripts/export_openapi.py --check
```

## Why this package exists

In the POC every response type was transcribed from Pydantic into TypeScript by hand, and
`await response.json()` is an unchecked cast, so neither side could notice a mismatch. It was
already wrong: `entity_types` was declared as a flat array where the API returns a mapping keyed by
kind, options were keyed on `value` instead of `entity_type`, a `sexes` list was invented, and
per-entity `complexities` were typed as bilingual when they carry no label at all. Nothing failed a
build. It would have surfaced as an empty picker in front of a user.

## What a generated type does and does not prove

It describes the schema the engine *published*. It cannot prove the running engine matches it — the
committed document could be stale. That half is `python scripts/export_openapi.py --check` in CI,
plus the engine's own test suite.

## Usage

```ts
import type { Proposal, SolveRequest, PadnextAuditReport } from "@workspace/contracts";

const response = await fetch(`${engineUrl}/api/v1/solve`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ extraction } satisfies SolveRequest),
});
const proposal: Proposal = await response.json();

// A proposal is a DRAFT until a named person approves it. Never render one as an invoice.
if (proposal.status !== "APPROVED") { /* … */ }
```
