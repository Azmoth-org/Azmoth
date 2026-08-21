#!/usr/bin/env python3
"""Write the Soufflé fact files for a manual case, without running the engine.

Useful for inspecting exactly what the rules engine is given, and for running Soufflé by hand:

    python scripts/generate_facts.py --manual manual_cases/case_001_knee/input.json -o facts/
    souffle -F facts -D out app/rules/goae_rules.dl
    column -t out/blocked_exclusion.csv
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ENGINE_ROOT))

from app.bridge.entity_to_ziffer import map_extraction  # noqa: E402
from app.catalog import load_catalog  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.schemas import ClinicalExtraction  # noqa: E402
from app.solvers.souffle_facts import INPUT_RELATIONS, write_fact_files  # noqa: E402
from app.rules.rule_store import RuleStore  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--manual", required=True, help="manual extraction JSON")
    parser.add_argument("-o", "--out", default="facts", help="output directory (default: facts/)")
    parser.add_argument(
        "--factors",
        help="optional JSON object of {ziffer: factor}, to exercise the § 5 / § 12 checks",
    )
    args = parser.parse_args()

    path = Path(args.manual)
    if not path.exists():
        print(f"error: {path} does not exist", file=sys.stderr)
        return 2

    payload = json.loads(path.read_text(encoding="utf-8"))
    if "extraction" in payload and isinstance(payload["extraction"], dict):
        payload = payload["extraction"]
    extraction = ClinicalExtraction.model_validate(payload)

    settings = get_settings()
    catalog = load_catalog(settings.catalog_path)
    rules = RuleStore.load(settings.rules_data_dir, policy=settings.unverified_rule_policy)
    bridge = map_extraction(extraction, catalog, rules)

    from decimal import Decimal

    proposed_factors = (
        {z: Decimal(str(f)) for z, f in json.loads(args.factors).items()} if args.factors else None
    )

    fact_dir = Path(args.out)
    counts = write_fact_files(fact_dir, catalog, rules, bridge, extraction, proposed_factors)

    print(f"catalog {catalog.catalog_version} · {len(rules.exclusions)} enforced exclusion rules")
    print(f"facts written to {fact_dir}/\n")
    for relation in INPUT_RELATIONS:
        print(f"  {relation + '.facts':<24} {counts[relation]:>5} rows")

    if bridge.warnings:
        print("\nwarnings:")
        for warning in bridge.warnings:
            print(f"  [{warning.severity}] {warning.type}: {warning.message[:100]}")

    print(f"\nnext: souffle -F {fact_dir} -D out {settings.datalog_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
