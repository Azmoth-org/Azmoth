"""Property tests over randomly generated small candidate sets.

The invariants below must hold for *any* input, not just the bundled cases. The generator is
seeded, so a failure is reproducible; the seed is printed in the assertion message.
"""

from __future__ import annotations

import random
from decimal import Decimal

import pytest

from app.validation.validator import ValidationFailed, cent_to_eur, line_amount_cent
from tests.conftest import make_bridge, make_extraction

#: Real positions drawn from several Abschnitte, so the § 5 bands, the mutual clusters, the
#: specificity pair and the Zielleistung pair all get exercised.
POOL = [
    "1", "3", "5", "6", "7", "8",        # Abschnitt B, one big mutual cluster
    "200", "300", "301", "302",          # Abschnitt C, specificity + Zielleistung
    "410", "422", "423", "424",          # Abschnitt C, echo cluster
    "650", "651", "652", "653", "659",   # Abschnitt F, EKG cluster
    "3550", "3560", "3741",              # Abschnitt M, tight band
    "4800",                              # Abschnitt N, general band
    "5030",                              # Abschnitt O, reduced band
]

SEVERITIES = [None, "leicht", "mittel", "schwer"]
SETTINGS = ["ambulant", "stationaer", "belegarzt"]

CASE_COUNT = 60


def generate_case(seed: int):
    rng = random.Random(seed)
    size = rng.randint(1, 6)
    ziffern = rng.sample(POOL, size)

    specs = []
    for index, ziffer in enumerate(ziffern, start=1):
        confidence = f"{rng.choice([0.4, 0.6, 0.75, 0.9, 1.0]):.2f}"
        # Occasionally put two candidates on one act, which is what triggers specificity.
        act = f"a{index}" if rng.random() > 0.2 or index == 1 else "a1"
        specs.append((act, ziffer, rng.choice([80, 100]), confidence))

    severity = rng.choice(SEVERITIES)
    justifications = (
        [{"reason": f"seed {seed} circumstance", "severity": severity}] if severity else []
    )
    extraction = make_extraction(
        setting=rng.choice(SETTINGS), justifications=justifications
    )
    return make_bridge(*specs), extraction, ziffern


def run(pipeline, bridge, extraction):
    rules_result = pipeline.apply_rules(extraction, bridge)
    optimization = pipeline.optimize(rules_result, extraction, bridge)
    verification_bridge = pipeline.validator.build_verification_bridge(optimization)
    verification = pipeline.apply_rules(
        extraction,
        verification_bridge,
        proposed_factors={f.ziffer: f.factor for f in optimization.factors},
    )
    coding, _audit = pipeline.validator.build(
        extraction, rules_result, optimization, bridge, verification=verification
    )
    return rules_result, optimization, coding


@pytest.mark.parametrize("seed", range(CASE_COUNT))
def test_random_case_satisfies_every_invariant(pipeline, catalog, rules, seed):
    bridge, extraction, ziffern = generate_case(seed)
    context = f"seed={seed} ziffern={ziffern} setting={extraction.patient.setting}"

    try:
        rules_result, optimization, coding = run(pipeline, bridge, extraction)
    except ValidationFailed as exc:  # pragma: no cover - a failure here is the point of the test
        pytest.fail(f"{context}: validation failed: {[v.model_dump() for v in exc.violations]}")

    charged = {line.ziffer for line in coding.proposed_codes}

    # 1. no enforced exclusion is violated
    for rule in rules.exclusions:
        assert not (rule.from_ziffer in charged and rule.to_ziffer in charged), (
            f"{context}: {rule.rule_id} violated"
        )

    # 2. no enforced Zielleistung rule is violated
    for zrule in rules.zielleistung:
        assert not (zrule.parent_ziffer in charged and zrule.child_ziffer in charged), (
            f"{context}: {zrule.rule_id} violated"
        )

    # 3. every factor is inside its legal band
    for line in coding.proposed_codes:
        band = catalog.factor_band(line.ziffer)
        cap = rules.factor_cap(line.ziffer)
        ceiling = min(band.max, cap.max_factor) if cap else band.max
        assert Decimal(1) <= line.factor <= ceiling, (
            f"{context}: GOÄ {line.ziffer} factor {line.factor} outside [1, {ceiling}]"
        )
        if line.factor > band.threshold:
            assert line.justification_present, (
                f"{context}: GOÄ {line.ziffer} above the Schwellenwert without a reason"
            )

    # 4. every charged position exists in the catalog and is active
    for ziffer in charged:
        assert catalog.has(ziffer), f"{context}: GOÄ {ziffer} not in catalog"
        assert catalog.is_active(ziffer), f"{context}: GOÄ {ziffer} inactive"

    # 5. every blocked position has a reason
    for blocked in coding.blocked_codes:
        assert blocked.reason, f"{context}: GOÄ {blocked.ziffer} blocked without a reason"
        assert blocked.explanation, f"{context}: GOÄ {blocked.ziffer} blocked without explanation"

    # 6. the total equals the sum of the lines
    line_sum = sum((line.amount_eur for line in coding.proposed_codes), Decimal(0))
    assert line_sum == coding.total.amount_eur, f"{context}: total mismatch"

    # 7. money matches the statutory formula on every line
    rate = catalog.minderung_rate(extraction.patient.setting)
    for line in coding.proposed_codes:
        effective = Decimal(0) if catalog.minderung_exempt(line.ziffer) else rate
        expected = cent_to_eur(
            line_amount_cent(line.punkte, line.factor, catalog.punktwert_cent)
            * (Decimal(1) - effective)
        )
        assert line.amount_eur == expected, f"{context}: GOÄ {line.ziffer} amount"

    # 8. the solver invented nothing
    proposed = {c.ziffer for c in rules_result.proposed}
    analog = {a.ziffer for a in optimization.analogs}
    assert charged <= proposed | analog, f"{context}: charged a position nobody proposed"

    # 9. every charged line carries a proof
    for line in coding.proposed_codes:
        assert line.proof, f"{context}: GOÄ {line.ziffer} has no proof"

    # 10. a mutual cluster never loses all its members.
    #
    # The unit is the CLUSTER, not the pair. Nr. 650-653 form a clique, so charging one member
    # necessarily leaves some individual pairs with neither side charged — that is correct, since
    # the law permits exactly one of them. What must never happen is a whole cluster vanishing,
    # which is the failure mode plain negation-as-failure produces.
    parent: dict[str, str] = {}

    def find(z: str) -> str:
        parent.setdefault(z, z)
        while parent[z] != z:
            parent[z] = parent[parent[z]]
            z = parent[z]
        return z

    def union(a: str, b: str) -> None:
        parent[find(a)] = find(b)

    for conflict in rules_result.conflicts:
        union(conflict.ziffer_a, conflict.ziffer_b)

    clusters: dict[str, set[str]] = {}
    for ziffer in list(parent):
        clusters.setdefault(find(ziffer), set()).add(ziffer)

    for members in clusters.values():
        assert members & charged, f"{context}: the whole cluster {sorted(members)} was dropped"
        assert len(members & charged) == 1, (
            f"{context}: {sorted(members & charged)} charged from one mutual cluster"
        )


@pytest.mark.parametrize("seed", range(12))
def test_random_case_is_deterministic(pipeline, seed):
    bridge_a, extraction_a, ziffern = generate_case(seed)
    bridge_b, extraction_b, _ = generate_case(seed)

    _r1, _o1, first = run(pipeline, bridge_a, extraction_a)
    _r2, _o2, second = run(pipeline, bridge_b, extraction_b)

    assert first.model_dump(mode="json") == second.model_dump(mode="json"), (
        f"seed={seed} ziffern={ziffern} produced two different results"
    )


@pytest.mark.parametrize("seed", range(12))
def test_minderung_never_increases_the_amount(pipeline, seed):
    bridge, extraction, ziffern = generate_case(seed)
    extraction.patient.setting = "ambulant"
    _r, _o, ambulant = run(pipeline, bridge, extraction)

    bridge2, extraction2, _ = generate_case(seed)
    extraction2.patient.setting = "stationaer"
    _r2, _o2, stationaer = run(pipeline, bridge2, extraction2)

    assert stationaer.total.amount_eur <= ambulant.total.amount_eur, f"seed={seed} {ziffern}"
    assert stationaer.total.punkte == ambulant.total.punkte
