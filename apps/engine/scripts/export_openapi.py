#!/usr/bin/env python3
"""Export the engine's OpenAPI document to `packages/contracts/openapi/openapi.json`.

    python scripts/export_openapi.py                 # write the default location
    python scripts/export_openapi.py --check         # fail if the committed file is stale
    python scripts/export_openapi.py -o /tmp/x.json  # somewhere else

Why this exists rather than a hand-written TypeScript mirror. In the POC every response type was
transcribed from Pydantic into TypeScript by hand, and `await response.json()` is an unchecked
cast, so nothing on either side could notice a mismatch. It was already wrong when we looked:
`entity_types` was declared as a flat array when the API returns a mapping keyed by kind, options
were keyed on `value` instead of `entity_type`, a `sexes` list was invented, and per-entity
`complexities` were typed as bilingual when they carry no label at all. None of it failed a build.
It would have surfaced as an empty picker.

The document is generated from the running app's own schema — no server needed, no network — and
committed, so a schema change shows up in a diff and a front-end build never depends on a live
engine. `--check` is what CI runs.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE_ROOT))

from app.config import REPO_ROOT  # noqa: E402

DEFAULT_OUTPUT = REPO_ROOT / "packages" / "contracts" / "openapi" / "openapi.json"


def build() -> dict:
    from app.main import app

    return app.openapi()


def render(document: dict) -> str:
    return json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-o", "--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="do not write; exit non-zero if the file on disk differs from the current schema",
    )
    args = parser.parse_args(argv)

    document = build()
    rendered = render(document)
    paths = len(document.get("paths", {}))
    schemas = len(document.get("components", {}).get("schemas", {}))

    if args.check:
        if not args.output.is_file():
            print(f"missing: {args.output}\nrun: python scripts/export_openapi.py", file=sys.stderr)
            return 1
        if args.output.read_text(encoding="utf-8") != rendered:
            print(
                f"stale: {args.output} does not match the current API schema.\n"
                "run: python scripts/export_openapi.py && pnpm --filter @workspace/contracts generate",
                file=sys.stderr,
            )
            return 1
        print(f"up to date: {args.output} ({paths} paths, {schemas} schemas)")
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(f"wrote {args.output} ({paths} paths, {schemas} schemas)")
    print("next: pnpm --filter @workspace/contracts generate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
