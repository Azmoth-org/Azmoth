"""Six invariants that must hold for *every* valid request, not for three golden cases.

Each test states one claim, recomputed from the catalog rather than read back off the response, and
Hypothesis looks for a request that breaks it. The generator is described in
`tests/property/conftest.py`; the short version is that it builds real `POST /api/v1/solve` bodies
out of the mapping table the bridge reads, and runs them through `Pipeline.propose` with the result
cache off.

**`test_financial_sum_invariant`** — Punktzahl x Punktwert x Faktor, less § 6a Minderung, rounded
half-up per line and summed, equals `total.amount_eur`. A failure means the invoice does not add
up, which is the most serious thing this file can tell you.

**`test_uniqueness_invariant`** — no Ziffer appears twice, and the lines are in a stable order. A
failure means the solver duplicated a position, or that two identical inputs cannot produce one
receipt.

**`test_proof_invariant`** — every position, charged or blocked, carries its reason. A failure
means a physician cannot answer a Rechnungsprüfer who asks "why".

**`test_factor_bounds_invariant`** — every factor is inside [Einfachsatz, Höchstsatz], and anything
above the Schwellenwert carries a written reason. A failure means the engine is billing a
multiplier the law does not permit.

**`test_determinism_invariant`** — the same request twice produces the same `receipt_hash`. A
failure means the receipt attests to nothing.

**`test_analog_positions_obey_the_same_hard_rules`** — a position charged analogously under § 6
Abs. 2 GOÄ is subject to the exclusion table and to § 4 Abs. 2a exactly as a directly billed one
is, and a candidate the invoice rules out is *reported* rather than silently skipped. A failure
means the § 6 Abs. 2 ladder can put a position on an invoice that the law does not allow there —
which is the defect recorded as F-1 in `docs/audit/PROPERTY_TEST_FINDINGS.md`.

**Two of these are also checked inside the engine, and that is the point.**
`app.validation.validator` re-checks the factor bands and the total independently of the solver,
and raises `ValidationFailed` when they disagree. So a broken engine has two ways to fail here:
the assertion below fires, or the validator raises first. Both are failures of the property and
`_solve` treats them the same way, because what these tests establish is that neither happens
across the whole generated input space — not that the validator's arithmetic agrees with itself.

Every monetary comparison uses `Decimal`. No float appears anywhere in this file, including in the
generated input: see `CONFIDENCES` in the conftest.

    .venv/bin/python -m pytest tests/property/ --hypothesis-seed=0
"""

from __future__ import annotations

import os
from decimal import Decimal
from typing import Any

import pytest
from hypothesis import event, given, note
from hypothesis import settings as hypothesis_settings

from app.catalog import Catalog
from app.rules.rule_store import RuleStore
from app.schemas import Coding, Proposal
from app.services.pipeline import Pipeline
from app.validation.validator import ValidationFailed, cent_to_eur, line_amount_cent
from tests.property.conftest import (
    ANALOG_EXCLUSION_REGION,
    ANALOG_TYPES,
    CATALOG,
    REACHABLE_ZIFFERN,
    RULES,
    analog_exclusion_requests,
    solve,
    solve_requests,
)

#: Examples per property. Measured at ~80 ms per solve (see `tests/README.md`), so 100 examples is
#: ~8 s of real solving per test — enough to cover the generated space several times over while
#: keeping this file inside the time budget of a suite people run before every commit.
#:
#: `HYPOTHESIS_MAX_EXAMPLES` raises it without editing anything, which is what a nightly sweep
#: wants and how the bugs recorded in `docs/property-testing.md` were found:
#:
#:     HYPOTHESIS_MAX_EXAMPLES=2000 .venv/bin/python -m pytest tests/property/ \
#:         --hypothesis-seed=random --hypothesis-show-statistics
#:
#: Nothing asserted here depends on the number.
MAX_EXAMPLES = int(os.getenv("HYPOTHESIS_MAX_EXAMPLES", "100"))

#: `test_determinism_invariant` solves twice per example, so it buys half as many examples for the
#: same wall-clock. It can afford that: the property is about one input at a time — two runs of a
#: given request either agree or they do not — so breadth is worth less here than it is to the four
#: properties that are looking for a request nobody thought of.
DETERMINISM_EXAMPLES = max(1, MAX_EXAMPLES // 2)

#: The § 5 Abs. 1 base rate. The floor of every legal factor band, by definition rather than by
#: catalog data — there is no Ziffer whose Einfachsatz is anything other than 1.0.
EINFACHSATZ = Decimal(1)


def _solve(pipeline: Pipeline, payload: dict[str, Any]) -> tuple[Proposal, Coding]:
    """Run one generated request, and treat a layer disagreement as the failure it is.

    `ValidationFailed` means the validator contradicted the solver — per
    `app.validation.validator`, a defect in the engine rather than in the input. It becomes a
    named failure here so that Hypothesis shrinks toward the smallest request that triggers it,
    and so the violations reach the report.
    """
    try:
        proposal = solve(pipeline, payload)
    except ValidationFailed as exc:
        pytest.fail(
            "the validator contradicted the solver: "
            + "; ".join(
                f"{v.code}({v.ziffer or '-'}): {v.message}" for v in exc.violations
            )
        )

    coding = proposal.solver_result.coding
    note(
        f"charged={[line.ziffer for line in coding.proposed_codes]} "
        f"blocked={[b.ziffer for b in coding.blocked_codes]} "
        f"setting={proposal.solver_result.extraction.patient.setting} "
        f"total={coding.total.amount_eur}"
    )
    # Visible under `--hypothesis-show-statistics`. A property suite whose generator quietly
    # collapsed to one-line invoices would still pass every assertion below, and this is how that
    # is noticed rather than assumed away.
    event(f"accepted positions: {len(coding.proposed_codes)}")
    event(f"blocked positions: {len(coding.blocked_codes)}")
    return proposal, coding


# ------------------------------------------------------------------------------------------
# 1. the money
# ------------------------------------------------------------------------------------------


@given(payload=solve_requests())
@hypothesis_settings(max_examples=MAX_EXAMPLES)
def test_financial_sum_invariant(
    property_pipeline: Pipeline, catalog: Catalog, payload: dict[str, Any]
) -> None:
    """The invoice adds up, from the statutory formula, exactly.

        Gebühr = Punktzahl x Punktwert x Steigerungsfaktor     § 5 Abs. 1 Satz 1-3 GOÄ
        - 25 % / - 15 % stationär / belegärztlich              § 6a Abs. 1 GOÄ
        halbe Cent aufwärts                                    § 5 Abs. 1 Satz 4 GOÄ

    Recomputed from the catalog, not from the response: `punkte` comes from `catalog.get()` and the
    Minderung rate from `catalog.minderung_rate()`, so the only numbers taken from the engine are
    the ones it is the engine's job to decide — which positions and which factors.

    Two clauses of the formula deserve naming, because the naive "sum of points x factor x
    Punktwert equals the total" is *false* for this engine and would be a weaker test, not a
    stronger one:

    * **§ 6a Minderung.** A stationär invoice is reduced by 25 %, per line, except for the
      positions the catalog marks exempt. For `setting='ambulant'` the rate is 0 and the formula
      does reduce to the naive one — which is why generating all three settings matters.
    * **Rounding is per line, then summed.** Each line is rounded half-up to the cent before it is
      added, because that is what the invoice shows and what the patient pays. Rounding the sum
      instead would differ by cents on multi-line invoices, and the difference would be real money.
    """
    proposal, coding = _solve(property_pipeline, payload)

    punktwert = catalog.punktwert_cent
    setting = proposal.solver_result.extraction.patient.setting
    minderung_rate = catalog.minderung_rate(setting)

    expected_total = Decimal(0)
    expected_punkte = 0

    for line in coding.proposed_codes:
        entry = catalog.get(line.ziffer)
        assert entry is not None, f"GOÄ {line.ziffer} is charged but not in the catalog"

        rate = Decimal(0) if catalog.minderung_exempt(line.ziffer) else minderung_rate
        gross_cent = line_amount_cent(entry.punkte, line.factor, punktwert)
        net_cent = gross_cent * (Decimal(1) - rate)

        # Unrounded first: this is the one comparison with no rounding on either side, so it
        # catches an arithmetic error that per-cent rounding would otherwise absorb.
        assert line.amount_cent_unrounded == net_cent, (
            f"GOÄ {line.ziffer}: unrounded {line.amount_cent_unrounded} cent, expected "
            f"{net_cent} = {entry.punkte} x {line.factor} x {punktwert} x (1 - {rate})"
        )
        assert line.amount_eur == cent_to_eur(net_cent), f"GOÄ {line.ziffer}: rounded amount"
        assert line.amount_eur_before_minderung == cent_to_eur(gross_cent), (
            f"GOÄ {line.ziffer}: amount before § 6a Minderung"
        )
        assert line.punkte == entry.punkte, f"GOÄ {line.ziffer}: Punktzahl is not the catalog's"
        assert line.minderung_applied == (rate > 0), f"GOÄ {line.ziffer}: Minderung flag"

        expected_total += cent_to_eur(net_cent)
        expected_punkte += entry.punkte

    assert coding.total.amount_eur == expected_total, (
        f"total {coding.total.amount_eur} EUR, but the lines sum to {expected_total} EUR"
    )
    assert coding.total.punkte == expected_punkte, "total Punktzahl is not the sum of the lines"
    assert coding.total.punktwert_cent == punktwert, "the invoice used another Punktwert"
    assert coding.total.minderung_rate == minderung_rate, (
        f"setting {setting!r} carries a § 6a rate of {minderung_rate}, invoice says "
        f"{coding.total.minderung_rate}"
    )


# ------------------------------------------------------------------------------------------
# 2. uniqueness
# ------------------------------------------------------------------------------------------


@given(payload=solve_requests())
@hypothesis_settings(max_examples=MAX_EXAMPLES)
def test_uniqueness_invariant(property_pipeline: Pipeline, payload: dict[str, Any]) -> None:
    """No Ziffer appears twice on one invoice, and the lines are in a stable order.

    The generator samples the mapping table *with replacement*, so a request may document the same
    service two or three times over. That is what makes this test worth running: without it the
    property would be a tautology over a set the generator had already deduplicated.

    The ordering clause is not decoration. `receipt_hash` covers the canonical response, so two
    runs that charged the same positions in a different order would produce two receipts for one
    billing decision — `test_determinism_invariant` would catch it as non-determinism without
    saying what moved. This says what moved.

    A charged position must also not appear among the blocked ones. "GOÄ 301 is on the invoice"
    and "GOÄ 301 was suppressed" cannot both be true, and an audit trail asserting both is worse
    than one asserting neither.
    """
    _proposal, coding = _solve(property_pipeline, payload)

    charged = [line.ziffer for line in coding.proposed_codes]
    assert len(charged) == len(set(charged)), f"a Ziffer is charged twice: {sorted(charged)}"
    assert charged == sorted(set(charged)), f"invoice lines are not in canonical order: {charged}"

    blocked = {entry.ziffer for entry in coding.blocked_codes}
    assert not (set(charged) & blocked), (
        f"{sorted(set(charged) & blocked)} are charged and reported as blocked at the same time"
    )


# ------------------------------------------------------------------------------------------
# 3. the proof
# ------------------------------------------------------------------------------------------


@given(payload=solve_requests())
@hypothesis_settings(max_examples=MAX_EXAMPLES)
def test_proof_invariant(property_pipeline: Pipeline, payload: dict[str, Any]) -> None:
    """Every position carries its reason — the charged ones and the absent ones.

    A blocked position with no explanation is the failure mode that makes an engine unusable in
    practice: the physician sees a service they performed missing from the draft and has no way to
    find out whether that was the law or a bug. So a blocked entry must carry both the
    human-readable `explanation` and the Datalog `proof` steps it was derived from.

    The blocker must also be on the final invoice. The layers interact — a position can be
    suppressed during rule evaluation by a position that then loses an arbitration — and
    "verdrängt durch GOÄ 7" is a misleading statement about an invoice that does not contain
    GOÄ 7. `Validator._reconcile_blocked` is what keeps that honest, by marking an entry whose
    blocker fell away as unreconciled and warning instead; this asserts the reconciled ones really
    are reconciled. `conflict_lost` is exempt because it names no single blocker: it is the outcome
    of an arbitration between members of a cluster, not a suppression by one position.
    """
    _proposal, coding = _solve(property_pipeline, payload)

    charged = {line.ziffer for line in coding.proposed_codes}

    for line in coding.proposed_codes:
        assert line.proof, f"GOÄ {line.ziffer} is charged with no proof tree"

    for entry in coding.blocked_codes:
        assert entry.explanation, f"GOÄ {entry.ziffer} is blocked without an explanation"
        assert entry.proof, f"GOÄ {entry.ziffer} is blocked without a single proof atom"
        if entry.reason != "conflict_lost" and entry.reconciled_with_final_invoice:
            assert entry.blocked_by in charged, (
                f"GOÄ {entry.ziffer} is reported as blocked by GOÄ {entry.blocked_by}, which is "
                "not on the invoice"
            )


# ------------------------------------------------------------------------------------------
# 4. the factor bands
# ------------------------------------------------------------------------------------------


@given(payload=solve_requests())
@hypothesis_settings(max_examples=MAX_EXAMPLES)
def test_factor_bounds_invariant(
    property_pipeline: Pipeline, catalog: Catalog, rules: RuleStore, payload: dict[str, Any]
) -> None:
    """Every charged factor is inside its legal band, and justified when it has to be.

    The band is `[Einfachsatz, Höchstsatz]` = `[1.0, catalog.factor_band(ziffer).max]`, narrowed
    further by any Leistungslegende cap in `data/rules/factor_caps.csv` — a cap below the § 5
    ceiling wins, because both are binding and the invoice has to satisfy both.

    Above the Schwellenwert the band is not the whole constraint: § 12 Abs. 3 GOÄ requires a
    written reason on the invoice, and a factor of 2.4 without one is as unlawful as a factor of
    4.0. The generator draws justifications at three severities and also draws requests with none
    at all, so both sides of that threshold are reached.

    Note what is *not* asserted: that the factor is as high as the law would allow. Choosing it is
    the solver's job and the ladder in `logic/asp/goae_optimize.lp` is where that decision lives —
    a property test that pinned the choice would be a golden test with extra steps.
    """
    _proposal, coding = _solve(property_pipeline, payload)

    for line in coding.proposed_codes:
        band = catalog.factor_band(line.ziffer)
        cap = rules.factor_cap(line.ziffer)
        ceiling = min(band.max, cap.max_factor) if cap else band.max

        assert EINFACHSATZ <= line.factor <= ceiling, (
            f"GOÄ {line.ziffer}: factor {line.factor} is outside [{EINFACHSATZ}, {ceiling}]"
            + (f" (capped by {cap.rule_id})" if cap else f" (§ 5 band max {band.max})")
        )
        if line.factor > band.threshold:
            assert line.justification_present, (
                f"GOÄ {line.ziffer}: factor {line.factor} is above the Schwellenwert "
                f"{band.threshold} with no written reason (§ 12 Abs. 3 GOÄ)"
            )
        event(f"factor basis: {line.factor_basis}")


# ------------------------------------------------------------------------------------------
# 5. determinism
# ------------------------------------------------------------------------------------------


@given(payload=solve_requests())
@hypothesis_settings(max_examples=DETERMINISM_EXAMPLES)
def test_determinism_invariant(property_pipeline: Pipeline, payload: dict[str, Any]) -> None:
    """The same request, solved twice, produces the same receipt.

    This is the property the whole design rests on. `receipt_hash` covers the catalog, the rule
    tables, the logic programs, both solver versions, the policy settings, the canonical input and
    the canonical output; the claim a Rechnungsprüfer can check is that two responses carrying one
    hash were produced by one of everything. If the hash moves between two identical requests, the
    hash identifies nothing and the audit trail is decoration.

    `cached is False` on both runs is asserted first, and it is not a detail: `Pipeline.propose` is
    content-addressed, so with the cache on the second run would return the first run's stored dict
    and this test would pass without the engine having solved anything. `property_pipeline` runs
    with `cache_enabled=False` — this asserts that it really did.

    The codings are compared before the hashes. Both comparisons must hold, but a diff between two
    `Coding` objects says *which line moved*, where a diff between two SHA-256 digests says only
    that something did.
    """
    first = solve(property_pipeline, payload)
    second = solve(property_pipeline, payload)

    assert not first.cached and not second.cached, (
        "the result cache served one of these runs, so this example proved nothing"
    )
    assert first.solver_result.coding == second.solver_result.coding, (
        "two identical requests produced two different invoices"
    )
    assert first.receipt_hash == second.receipt_hash, (
        f"two identical requests produced two receipts: {first.receipt_hash} != "
        f"{second.receipt_hash}"
    )
    assert len(first.receipt_hash) == 64, "a receipt is a SHA-256 digest"


# ------------------------------------------------------------------------------------------
# 6. the § 6 Abs. 2 Analogansatz obeys the same hard rules
# ------------------------------------------------------------------------------------------


def _incompatible(a: str, b: str) -> bool:
    """Whether two positions may not both be charged, under either enforced relation.

    Read from `RULES`, which is loaded under the same `UnverifiedRulePolicy.WARN` the pipeline runs
    with, so this is the rule set that actually constrains an invoice. Both relations are checked
    in both directions: the ASP constraints forbid *co-occurrence*, so which way round the CSV
    happened to state a pair does not change what is billable.
    """
    if any(
        {rule.from_ziffer, rule.to_ziffer} == {a, b} for rule in RULES.exclusions
    ):
        return True
    return any(
        {rule.parent_ziffer, rule.child_ziffer} == {a, b} for rule in RULES.zielleistung
    )


def _analog_candidates(payload: dict[str, Any]) -> dict[str, set[str]]:
    """The § 6 Abs. 2 ladder each documented Analogansatz service will be offered.

    Keyed by entity type, filtered to positions the catalog has and lists as active — the same
    filter `ClingoSolver.build_facts` applies before injecting `analog_cand/3`, so this is the
    candidate set the solver actually chooses from rather than every row in the table.
    """
    documented = {
        entity["type"]
        for entity in payload["extraction"].get("procedures", [])
        if entity["type"] in ANALOG_TYPES
    }
    return {
        entity_type: {
            rule.target_ziffer
            for rule in RULES.analog_for(entity_type)
            if CATALOG.has(rule.target_ziffer) and CATALOG.is_active(rule.target_ziffer)
        }
        for entity_type in documented
    }


@given(payload=analog_exclusion_requests())
@hypothesis_settings(max_examples=MAX_EXAMPLES)
def test_analog_positions_obey_the_same_hard_rules(
    property_pipeline: Pipeline, payload: dict[str, Any]
) -> None:
    """An Analogansatz position is a charge, and faces every constraint a charge faces.

    § 6 Abs. 2 GOÄ lets an unlisted service be billed as an equivalent listed one. It does not
    exempt the result from anything: the position that ends up on the invoice is subject to the
    Leistungslegenden exclusions and to the Zielleistungsprinzip (§ 4 Abs. 2a) exactly as it would
    be if the bridge had proposed it directly. That is one claim, and it has three halves here:

    * **The invoice is legal.** No enforced exclusion and no Zielleistung pair survives on it,
      whichever rule put each position there. This is what fails if the two hard constraints in
      `logic/asp/goae_optimize.lp` are ever narrowed back to `bill/1`.
    * **The engine answers.** Every documented § 6 Abs. 2 service is either charged analogously or
      named in an `analog_uncovered` warning. Both are answers; silence is not, and neither is the
      `500` this used to produce — `_solve` turns a validator contradiction into a named failure,
      so the original defect fails this test on the first half before reaching the second.
    * **A rejected rung is explained.** A candidate that the final invoice made unusable is
      reported as blocked, with a blocker that is really on the invoice and at least one proof
      atom. "Why not the closer candidate" is the first question anyone asks about an Analogansatz,
      and the § 6 Abs. 2 decision is not auditable if the response cannot answer it.

    The generator aims squarely at this region — see `analog_exclusion_requests` — because it is a
    narrow corner of a wide space that the five properties above reach only by luck.
    """
    _proposal, coding = _solve(property_pipeline, payload)

    charged = {line.ziffer for line in coding.proposed_codes}

    for rule in RULES.exclusions:
        assert not (rule.from_ziffer in charged and rule.to_ziffer in charged), (
            f"{rule.rule_id} is violated by {sorted(charged)}"
        )
    for rule in RULES.zielleistung:
        assert not (rule.parent_ziffer in charged and rule.child_ziffer in charged), (
            f"{rule.rule_id}: GOÄ {rule.child_ziffer} is charged next to its target service "
            f"GOÄ {rule.parent_ziffer} (§ 4 Abs. 2a GOÄ)"
        )

    ladders = _analog_candidates(payload)
    answered = {decision.entity_type for decision in coding.analog_codes} | {
        warning.type for warning in coding.warnings if warning.type == "analog_uncovered"
    }
    for entity_type in ladders:
        assert entity_type in answered or "analog_uncovered" in answered, (
            f"the documented Analogansatz service {entity_type!r} is neither charged analogously "
            "nor reported as uncoverable"
        )
        event(f"analog answered: {entity_type}")

    blocked = {entry.ziffer: entry for entry in coding.blocked_codes}
    for candidates in ladders.values():
        for candidate in sorted(candidates):
            blockers = sorted(w for w in charged if _incompatible(candidate, w))
            if not blockers:
                continue
            event("analog candidate ruled out by the invoice")
            assert candidate not in charged, (
                f"GOÄ {candidate} was charged as an Analogziffer next to "
                f"GOÄ {', '.join(blockers)}, which the rules do not allow"
            )
            entry = blocked.get(candidate)
            assert entry is not None, (
                f"GOÄ {candidate} could not be used as an Analogziffer because of "
                f"GOÄ {', '.join(blockers)}, and nothing in the response says so"
            )
            assert entry.explanation, f"GOÄ {candidate} is blocked without an explanation"
            assert entry.proof, f"GOÄ {candidate} is blocked without a single proof atom"
            assert entry.blocked_by in charged, (
                f"GOÄ {candidate} is reported as blocked by GOÄ {entry.blocked_by}, which is not "
                "on the invoice"
            )


def test_the_analog_ladder_respects_exclusions_against_the_final_invoice(
    property_pipeline: Pipeline,
) -> None:
    """The minimal case `test_uniqueness_invariant` shrank to, pinned as a regression test.

    A dermatoscopy (Nr. 750), a sonography (Nr. 410) and an organ-system examination (Nr. 7) are
    all documented directly. An optical coherence tomography is documented too — it has no Ziffer
    of its own, so § 6 Abs. 2 GOÄ charges it analogously, and its candidate ladder is Nr. 750
    (0.75), Nr. 410 (0.55), Nr. 5 (0.25).

    The first two candidates are already billed directly, and avoiding that collision is objective
    @5 — ranked above similarity at @2 — so the solver walks down to Nr. 5. **This is where the
    engine used to break.** Nr. 5 and Nr. 7 are mutually exclusive under `excl_man_5_7`, the fact
    is injected, and the constraint that would have used it looked only at `bill/1` — which an
    analog position never enters. The solver charged Nr. 5 anyway, the validator refused the
    invoice, and the caller got a `500` for an ordinary encounter. Recorded as F-1 in
    `docs/audit/PROPERTY_TEST_FINDINGS.md`, and reproduced here as an `xfail(strict=True)` until
    the constraints were widened to `charged/1`.

    Now Nr. 5 is unusable, the ladder goes back up to its closest candidate, and the collision is
    reported rather than dodged: Nr. 750 is charged once, for both the dermatoscopy and — as the
    analog position — the tomography, with `analog_collision` telling a human to look at it. That
    is a different invoice from the one the ladder was reaching for, and it is a legal one.

    The exact positions are asserted, not just the absence of a violation. The property test above
    covers "no exclusion is violated" across the whole region; what only this case can pin is
    *which* answer the objective ordering produces once the constraint is in force, so a future
    change to that ordering shows up here as a diff rather than as a silently different bill.
    """
    payload = {
        "extraction": {
            "patient": {"age": 50, "sex": "m", "setting": "ambulant"},
            "examinations": [{"type": "vollstaendige_untersuchung_organsystem"}],
            "procedures": [
                {"type": "dermatoskopie", "organ": "haut"},
                {"type": "sonographie"},
                {"type": "optische_kohaerenztomographie"},
            ],
        }
    }
    proposal = solve(property_pipeline, payload)
    coding = proposal.solver_result.coding

    charged = {line.ziffer for line in coding.proposed_codes}
    for rule in RULES.exclusions:
        assert not (rule.from_ziffer in charged and rule.to_ziffer in charged), (
            f"{rule.rule_id} is violated by {sorted(charged)}"
        )

    assert charged == {"7", "410", "750"}, (
        "the objective ordering no longer produces the invoice this case was frozen against"
    )
    assert "5" not in charged, "Nr. 5 is not chargeable next to Nr. 7 (excl_man_5_7)"

    # The analog position is the closest candidate, charged once and flagged for a human.
    assert [(d.entity_type, d.ziffer) for d in coding.analog_codes] == [
        ("optische_kohaerenztomographie", "750")
    ]
    assert any(w.type == "analog_collision" and w.ziffer == "750" for w in coding.warnings), (
        "Nr. 750 is charged both directly and as the Analogziffer — that must be reported"
    )

    # And the rung the invoice ruled out says so itself, with the verified rule that did it.
    rejected = next(entry for entry in coding.blocked_codes if entry.ziffer == "5")
    assert rejected.reason == "exclusion"
    assert rejected.blocked_by == "7"
    assert rejected.rule_id == "excl_man_5_7"
    assert rejected.explanation
    assert [step.rule for step in rejected.proof] == ["analog_candidate_blocked"]


# ------------------------------------------------------------------------------------------
# the generator itself
# ------------------------------------------------------------------------------------------


def test_the_generated_space_is_worth_exploring() -> None:
    """Guard against a property suite that passes because it generates nothing.

    The five properties above are all universally quantified, so they hold vacuously over an empty
    input space — a mapping table that stopped resolving against the catalog, or a filter that
    became too strict, would turn this whole file green while testing nothing. The counts are
    lower bounds, deliberately well under what the table currently offers, so an ordinary data
    change does not fail this and a collapse does.
    """
    assert len(REACHABLE_ZIFFERN) >= 20, (
        f"the strategies can only reach {len(REACHABLE_ZIFFERN)} positions: "
        f"{sorted(REACHABLE_ZIFFERN)}"
    )
    # The invariants that matter most are about interaction — exclusions, mutual clusters,
    # specificity — so the space has to contain positions the rules have something to say about.
    for cluster in (
        {"1", "3", "5", "7", "8"},          # Abschnitt B, one big mutual cluster
        {"300", "301", "302"},              # specificity: generic vs. joint-specific puncture
        {"650", "651", "659"},              # the EKG cluster
        {"422", "423", "424"},              # echocardiography, generic vs. Doppler
    ):
        assert cluster <= REACHABLE_ZIFFERN, f"{sorted(cluster - REACHABLE_ZIFFERN)} unreachable"

    # The region where a § 6 Abs. 2 ladder meets the exclusion table is the whole subject of
    # `test_analog_positions_obey_the_same_hard_rules`, and it is derived from the rule tables —
    # so an unrelated data change could empty it and leave that test passing over nothing. Pinned
    # here instead. This assertion used to say the opposite: it bounded a region the generator
    # *avoided*, because the engine returned a 500 for it. Widening is now welcome; vanishing is
    # not, which is why the analog type is named and the count is a floor.
    assert set(ANALOG_EXCLUSION_REGION) >= {"optische_kohaerenztomographie"}, (
        f"no Analogansatz type collides with the exclusion table any more: "
        f"{sorted(ANALOG_EXCLUSION_REGION)}"
    )
    assert ANALOG_EXCLUSION_REGION["optische_kohaerenztomographie"] >= {
        ("examination", "untersuchung_ganzkoerperstatus"),
        ("examination", "vollstaendige_untersuchung_organsystem"),
    }, "the analog/exclusion region shrank — that test now covers less than it did"
