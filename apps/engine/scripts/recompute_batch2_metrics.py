#!/usr/bin/env python3
"""Recompute every coverage figure the batch 2 report publishes, live off the repository.

    python scripts/recompute_batch2_metrics.py            # table
    python scripts/recompute_batch2_metrics.py --json     # machine-readable

Nothing here is typed from a previous run: the catalog, the rule store and the Ziffer sets are
all read at call time, and each figure prints the formula it came from.

Four words are kept strictly apart, because the report's headline number depends on which one is
meant:

**represented**   a Ziffer named by at least one loaded rule of a family. Says nothing about
                  whether anything ever evaluates it.
**enforceable**   the rule's family is wired into a Datalog layer that can remove a position, and
                  the facts that layer needs *can* be supplied by some caller.
**executable today (PADnext)**
                  the facts actually reach the layer on the shipped ingestion path. This is the
                  narrowest set and the honest denominator for a claim about what the product
                  does, as opposed to what the rule corpus contains. All three Batch 2 families
                  score zero here — see `_PADNEXT_NOTE`.
**counted**       included in the published `enforced_rule_count` / `total_constraint_rule_count`.
                  Batch 2 is deliberately *not*, which is why "enforced rules" did not move.

The overlap arithmetic is the other thing worth doing rather than assuming. 37 rows touch 37
distinct Ziffern (the three families are pairwise disjoint), but 14 of those Ziffern were already
named by an older exclusion/Zielleistung/specificity/factor-cap rule, so the count of Ziffern
under *any* rule grows by 23, not 37. Percentages are computed from the union and never added.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ENGINE_ROOT.parents[1]
sys.path.insert(0, str(ENGINE_ROOT))

from app.catalog.catalog_loader import load_catalog  # noqa: E402
from app.rules.rule_store import RULES_DATA_DIR, RuleStore  # noqa: E402

_PADNEXT_NOTE = (
    "no production call site supplies the fact this layer needs: "
    "`app/services/pipeline.py` calls `souffle.run(extraction, bridge, proposed_factors=...)` "
    "with no `history_counts`, and `app/padnext/audit.py::_build_group_audit_input` builds "
    "`Patient(setting=setting)`, leaving `age` and `sex` None"
)


def collect(rules: RuleStore) -> dict:
    """Every Ziffer set the report's arithmetic rests on."""
    counted_families = {
        "exclusions": {z for r in rules.exclusions for z in (r.from_ziffer, r.to_ziffer)},
        "zielleistung": {z for r in rules.zielleistung for z in (r.parent_ziffer, r.child_ziffer)},
        "specificity": {
            z for r in rules.specificity for z in (r.specific_ziffer, r.general_ziffer)
        },
        "factor_caps": {r.ziffer for r in rules.factor_caps},
    }
    batch2_families = {
        "quantity_limits": {r.ziffer for r in rules.quantity_limits},
        "gender_restrictions": {r.ziffer for r in rules.gender_restrictions},
        "age_restrictions": {r.ziffer for r in rules.age_restrictions},
        "time_relations": {z for r in rules.time_relations for z in (r.ziffer_a, r.ziffer_b)},
    }
    return {"counted": counted_families, "batch2": batch2_families}


def build(rules_dir: Path = RULES_DATA_DIR) -> dict:
    catalog = load_catalog()
    rules = RuleStore.load(rules_dir)
    sets = collect(rules)

    total_ziffern = len(catalog.ziffern)

    counted_union: set[str] = set()
    for members in sets["counted"].values():
        counted_union |= members
    batch2_union: set[str] = set()
    for members in sets["batch2"].values():
        batch2_union |= members

    batch2_rows = {
        "quantity_limits": len(rules.quantity_limits),
        "gender_restrictions": len(rules.gender_restrictions),
        "age_restrictions": len(rules.age_restrictions),
        "time_relations": len(rules.time_relations),
    }

    already = sorted(batch2_union & counted_union, key=lambda z: (len(z), z))
    newly = batch2_union - counted_union

    enforced = rules.enforced_rule_count()
    constraint_total = len(rules.constraint_rules())

    return {
        "catalog": {
            "total_ziffern": total_ziffern,
            "version": getattr(catalog, "catalog_version", None),
        },
        "published": {
            "enforced_rule_count": enforced,
            "total_constraint_rule_count": constraint_total,
            "ziffern_under_an_enforced_rule": len(counted_union),
            "pct_of_catalog": round(100 * len(counted_union) / total_ziffern, 2),
            "formula": "|union of exclusions/zielleistung/specificity/factor_caps Ziffern| / |catalog|",
        },
        "batch2": {
            "rows_total": sum(batch2_rows.values()),
            "rows_per_family": batch2_rows,
            "ziffern_per_family": {k: len(v) for k, v in sets["batch2"].items()},
            "distinct_ziffern": len(batch2_union),
            "families_pairwise_disjoint": sum(len(v) for v in sets["batch2"].values())
            == len(batch2_union),
            "already_under_an_older_rule": already,
            "already_count": len(already),
            "newly_represented": len(newly),
            "formula": "newly = |batch2 Ziffern| - |batch2 Ziffern already in the counted union|",
        },
        "if_batch2_were_counted": {
            "enforced_rule_count": enforced + sum(batch2_rows.values()),
            "total_constraint_rule_count": constraint_total + sum(batch2_rows.values()),
            "ziffern_under_a_rule": len(counted_union | batch2_union),
            "pct_of_catalog": round(100 * len(counted_union | batch2_union) / total_ziffern, 2),
        },
        "executable_today_on_padnext": {
            "quantity_limits": 0,
            "gender_restrictions": 0,
            "age_restrictions": 0,
            "time_relations": 0,
            "total": 0,
            "why": _PADNEXT_NOTE,
        },
        "enforceable_given_the_facts": {
            # Reachable through the general clinical-extraction API, which does let a caller
            # populate `Patient.age` / `Patient.sex`, and through any caller that computes
            # `history_counts` itself.
            "quantity_limits": batch2_rows["quantity_limits"],
            "gender_restrictions": batch2_rows["gender_restrictions"],
            "age_restrictions": batch2_rows["age_restrictions"],
            "time_relations": 0,
            "total": sum(batch2_rows.values()) - batch2_rows["time_relations"],
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rules-dir", type=Path, default=RULES_DATA_DIR)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    m = build(args.rules_dir)
    if args.json:
        print(json.dumps(m, indent=2, ensure_ascii=False))
        return 0

    cat, pub, b2, iff = m["catalog"], m["published"], m["batch2"], m["if_batch2_were_counted"]

    print(f"catalog                        : {cat['total_ziffern']} Ziffern ({cat['version']})")
    print()
    print("── Published (unchanged by batch 2) ───────────────────────────────────────────")
    print(f"  enforced_rule_count          : {pub['enforced_rule_count']}")
    print(f"  total_constraint_rule_count  : {pub['total_constraint_rule_count']}")
    print(
        f"  Ziffern under an enforced rule: {pub['ziffern_under_an_enforced_rule']}"
        f" / {cat['total_ziffern']}  ({pub['pct_of_catalog']}%)"
    )
    print(f"  formula                      : {pub['formula']}")
    print()
    print("── Batch 2 corpus ─────────────────────────────────────────────────────────────")
    print(f"  rows total                   : {b2['rows_total']}")
    for family, count in b2["rows_per_family"].items():
        print(f"    {family:26s} : {count:3d} row(s), {b2['ziffern_per_family'][family]:3d} Ziffer(n)")
    print(f"  distinct Ziffern             : {b2['distinct_ziffern']}")
    print(f"  families pairwise disjoint   : {b2['families_pairwise_disjoint']}")
    print(f"  already under an older rule  : {b2['already_count']}  {b2['already_under_an_older_rule']}")
    print(f"  newly represented            : {b2['newly_represented']}")
    print(f"  formula                      : {b2['formula']}")
    print()
    print("── If batch 2 were folded into the published counts ───────────────────────────")
    print(f"  enforced_rule_count          : {iff['enforced_rule_count']}")
    print(f"  total_constraint_rule_count  : {iff['total_constraint_rule_count']}")
    print(
        f"  Ziffern under a rule         : {iff['ziffern_under_a_rule']}"
        f" / {cat['total_ziffern']}  ({iff['pct_of_catalog']}%)"
    )
    print()
    print("── Executable today, PADnext ingestion ────────────────────────────────────────")
    ex = m["executable_today_on_padnext"]
    for family in ("quantity_limits", "gender_restrictions", "age_restrictions", "time_relations"):
        print(f"    {family:26s} : {ex[family]:3d}")
    print(f"  total                        : {ex['total']}")
    print(f"  why                          : {ex['why']}")
    print()
    print("── Enforceable given the facts (general extraction API) ───────────────────────")
    en = m["enforceable_given_the_facts"]
    for family in ("quantity_limits", "gender_restrictions", "age_restrictions", "time_relations"):
        print(f"    {family:26s} : {en[family]:3d}")
    print(f"  total                        : {en['total']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
