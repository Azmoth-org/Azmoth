"""Fixtures and input strategies for the Hypothesis invariant suite.

`tests/test_property.py` already asserts ten invariants over randomly generated *candidate sets*:
it builds a `BridgeResult` by hand from a curated pool of Ziffern and drives the symbolic layers
directly. This package is the other half of the same claim, and two things differ.

**What is generated.** A real `SolveRequest` — the frozen input contract, clinical entities only,
no Ziffer anywhere — rather than a synthetic bridge result. There is no way to ask this engine to
charge a Ziffer: the caller documents what happened and the bridge decides. So "a random valid
request with 1-10 positions" means 1-10 documented services drawn from `load_mapping()`, the exact
CSV the bridge reads, filtered against the loaded catalog.

That is where the real Ziffern come from. Every row carries the position it resolves to, and
`_billable_rows()` keeps only rows whose Ziffer the catalog both contains and lists as active — so
each generated service provably reaches a real, active position in the real GOÄ snapshot, and the
strategies cannot drift from the mapping table. Adding a row to the CSV widens them; removing one
narrows them; neither needs an edit here.

**How far it runs.** `Pipeline.propose`, exactly as `POST /api/v1/solve` calls it: bridge, Soufflé,
Clingo, the Soufflé re-check of the chosen factors, the validator, the receipt. That is what makes
`receipt_hash` available to assert on, and it is why the determinism property is about the receipt
a Rechnungsprüfer would be handed rather than about two Python objects comparing equal.

## One region the generator used to stay out of, and now aims at

An Analogansatz service documented alongside a service whose Ziffer is incompatible with one of
that analog type's § 6 Abs. 2 candidate targets. Until the analog/exclusion fix this combination
tripped an open defect — the two legality constraints in `logic/asp/goae_optimize.lp` ranged over
`bill/1`, which an analog position never enters, so the ladder could land on a position that is not
chargeable next to one already billed and the validator refused the whole invoice with a `500`
(F-1 in `docs/audit/PROPERTY_TEST_FINDINGS.md`). `_drop_defective_combinations()` kept the
generator out of it.

The constraints now range over `charged/1`, so the region is *targeted* instead of avoided. The
same derivation from the rule tables that used to be a filter is now a strategy:
`ANALOG_EXCLUSION_ROWS` pairs each analog entity type with the documented services that collide
with one of its candidates, and `analog_exclusion_requests()` builds requests that put the two
together on purpose. It is still derived rather than written out, so a new analog candidate or a
new exclusion widens the region automatically instead of quietly leaving it untested, and
`test_the_generated_space_is_worth_exploring` pins its current size.

## The cache is off

`Pipeline.propose` is content-addressed, and Hypothesis repeats inputs constantly — while shrinking,
and because a minimal example is generated over and over. With the cache on, most examples would
assert against a dict computed once, which is the opposite of what a property test is for. So
`property_pipeline` runs with `cache_enabled=False` and every example is genuinely solved.

## Reproducing a failure

The profile deliberately does **not** set `derandomize`, so a plain run explores new inputs — that
is the whole point of having these tests. Pin the input set to reproduce a failure, or to make a
build actionable:

    .venv/bin/python -m pytest tests/property/ --hypothesis-seed=0          # the documented run
    .venv/bin/python -m pytest tests/property/ --hypothesis-seed=random     # explore
    .venv/bin/python -m pytest tests/property/ --hypothesis-show-statistics # what got generated

`derandomize` is checked *before* `--hypothesis-seed` inside Hypothesis, so setting it in the
profile would have silently made the documented `--hypothesis-seed=0` a no-op. CI passes the flag
instead, which keeps a red build reproducible without freezing the input set for everybody.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import pytest
from hypothesis import settings as hypothesis_settings
from hypothesis import strategies as st

from app.bridge.entity_to_ziffer import COMPLEXITY_ALIASES, MappingRow, load_mapping
from app.catalog import Catalog, load_catalog
from app.config import RULES_DATA_DIR, Settings, UnverifiedRulePolicy
from app.rules.rule_store import RuleStore
from app.schemas import Proposal, SolveRequest
from app.services.pipeline import Pipeline
from tests.conftest import _require_or_skip

# `deadline=None` because a solve shells out to the `souffle` binary and grounds an ASP program:
# wall-clock is a property of the machine, not of the input, and the first example additionally
# pays for warm-up. A per-example time limit here would produce flaky failures that say nothing
# about the invariants. Runtime is bounded by `max_examples` on each test instead, and
# `tests/README.md` records what that costs.
hypothesis_settings.register_profile("engine", deadline=None, print_blob=True)
hypothesis_settings.load_profile("engine")


# ------------------------------------------------------------------------------------------
# fixtures
# ------------------------------------------------------------------------------------------


@pytest.fixture(scope="session")
def property_settings(settings: Settings) -> Settings:
    """The suite's settings with the result cache switched off. See the module docstring."""
    return settings.model_copy(update={"cache_enabled": False})


@pytest.fixture(scope="session")
def property_pipeline(
    property_settings: Settings, catalog: Catalog, rules: RuleStore
) -> Pipeline:
    """One pipeline for the whole session.

    Session-scoped is required, not merely faster: `@given` with a function-scoped fixture trips
    `HealthCheck.function_scoped_fixture`, and rightly so — pytest would build the fixture once and
    hand the same object to every example anyway, so a function-scoped one would only be lying
    about its lifetime. The pipeline holds no per-solve state once the cache is off.
    """
    pipeline = Pipeline(property_settings, catalog, rules)
    if not pipeline.souffle.available():
        _require_or_skip(property_settings)
    return pipeline


def solve(pipeline: Pipeline, payload: dict[str, Any]) -> Proposal:
    """Validate a generated payload and run it, exactly as `POST /api/v1/solve` does.

    The payload is a plain dict rather than a model so that each call parses its own
    `SolveRequest`: the pipeline mutates `patient.setting` and the extraction validator assigns
    entity ids, so two runs must not be handed one object. That is what makes the determinism
    property a statement about the engine rather than about aliasing.
    """
    request = SolveRequest.model_validate(payload)
    return pipeline.propose(
        request.extraction, setting=request.setting, case_id=request.case_id
    )


# ------------------------------------------------------------------------------------------
# where the real Ziffern come from
# ------------------------------------------------------------------------------------------

#: The catalog and rule set the strategies are built against, loaded at import time. `load_catalog`
#: is `lru_cache`d and takes the same arguments as the session `catalog` fixture, so this is the
#: same parsed object the pipeline under test is holding — not a second copy that could disagree.
CATALOG: Catalog = load_catalog()
RULES: RuleStore = RuleStore.load(RULES_DATA_DIR, policy=UnverifiedRulePolicy.WARN)

#: alias -> the `Complexity` literal the input contract accepts. The mapping table qualifies an
#: excision by size ("klein"/"gross"); the schema only knows "einfach"/"mittel"/"komplex", and the
#: bridge translates between them. A strategy that emitted the raw alias would be rejected by
#: Pydantic, and one that emitted the wrong complexity would map to nothing and silently charge
#: zero — the exact failure `app.bridge.vocabulary` exists to prevent in the UI.
ALIAS_TO_COMPLEXITY: dict[str, str] = {
    alias: complexity
    for complexity, aliases in COMPLEXITY_ALIASES.items()
    for alias in aliases
}


def _billable_rows() -> tuple[MappingRow, ...]:
    """Mapping rows whose Ziffer the loaded catalog contains and lists as active.

    The filter is the same hard invariant the bridge enforces in `map_extraction`: a Ziffer the
    catalog does not have can never be proposed. Applying it here means a generated service is
    never one the bridge would drop with a warning, so an empty invoice in these tests is a
    statement about the *rules*, never about the fixture data.
    """
    return tuple(
        row
        for row in load_mapping()
        if CATALOG.has(row.ziffer) and CATALOG.is_active(row.ziffer)
    )


ROWS: tuple[MappingRow, ...] = _billable_rows()

#: Entity types with no mapping row at all but a § 6 Abs. 2 Analogansatz candidate. Included so
#: the analog path — a position that was never a candidate and whose proof comes from the
#: verification pass — is inside the generated space rather than outside it.
ANALOG_TYPES: tuple[str, ...] = tuple(
    sorted({rule.source_entity_type for rule in RULES.analog_candidates})
)

#: Positions the strategies can actually put in play. Asserted on in the test module, so a mapping
#: table that shrank to nothing cannot leave the properties passing over an empty space.
REACHABLE_ZIFFERN: frozenset[str] = frozenset(row.ziffer for row in ROWS)


# ------------------------------------------------------------------------------------------
# strategies
# ------------------------------------------------------------------------------------------

#: Strings, not floats. `confidence` is a `Decimal` all the way down and the suite's rule is that
#: no float touches money or a Steigerungsfaktor; a generated float would be the one place one
#: could enter. The spread straddles `LOW_CONFIDENCE_THRESHOLD` (0.7) so the low-confidence
#: warning path is generated too.
CONFIDENCES = st.sampled_from(["0.40", "0.60", "0.75", "0.90", "1.00"])
COMPLEXITIES = st.sampled_from(["einfach", "mittel", "komplex"])
SETTINGS = st.sampled_from(["ambulant", "stationaer", "belegarzt"])
SEXES = st.sampled_from(["m", "w", "d"])
SEVERITIES = st.sampled_from(["leicht", "mittel", "schwer"])

#: Free text whose *content* nothing branches on — only its presence, which is what § 12 Abs. 3
#: requires. Sampled from a realistic handful rather than fuzzed with `st.text()`, so a falsifying
#: example reads like a case a physician could have written instead of like a Unicode puzzle.
REASONS = st.sampled_from(
    [
        "erschwerte Lagerung bei Adipositas",
        "unkooperativer Patient, erhöhter Zeitaufwand",
        "ausgedehnter Befund, mehrfache Kontrolle notwendig",
        "Notfall außerhalb der Sprechzeiten",
    ]
)


def _kind(row: MappingRow) -> str:
    """Which list of the extraction a row's service belongs in."""
    return row.kind if row.kind in {"consultation", "examination", "lab_test"} else "procedure"


def _service_type(row: MappingRow) -> str:
    """The `type` field a generated entity carries for this row.

    Not always `row.entity_type`: a lab test's `type` is the analyte, which the bridge reads back
    as the *subtype* under a fixed `entity_type='labor'`. Shared with `_entity` below so the guard
    and the builder cannot disagree about what a row produces.
    """
    return row.entity_subtype if _kind(row) == "lab_test" else row.entity_type


@lru_cache(maxsize=None)
def _entity(row: MappingRow) -> st.SearchStrategy[tuple[str, dict[str, Any]]]:
    """One documented service built from one mapping row, as `(kind, entity dict)`.

    The row's own `(entity_type, entity_subtype, organ)` key is reproduced field for field, which
    is what guarantees the bridge resolves it: `candidates_for_act` looks that triple up directly.
    Where the row says nothing, the strategy is free to vary — an organ-free row may still carry a
    complexity, because that column does not participate in its key.

    Cached per row (`MappingRow` is frozen, so it hashes) because `flatmap` calls this on every
    draw, and rebuilding a composite strategy thousands of times buys nothing.
    """
    kind = _kind(row)

    @st.composite
    def build(draw: Any) -> tuple[str, dict[str, Any]]:
        entity: dict[str, Any] = {"confidence": draw(CONFIDENCES)}

        entity["type"] = _service_type(row)

        if kind == "lab_test":
            return kind, entity

        if kind == "consultation":
            duration = draw(st.one_of(st.none(), st.integers(min_value=1, max_value=120)))
            if duration is not None:
                entity["duration_minutes"] = duration
            return kind, entity

        if row.entity_subtype in ALIAS_TO_COMPLEXITY:
            # This row is keyed on size, so the complexity is load-bearing and pinned.
            entity["complexity"] = ALIAS_TO_COMPLEXITY[row.entity_subtype]
        else:
            entity["complexity"] = draw(COMPLEXITIES)

        if row.organ:
            entity["organ_system" if kind == "examination" else "organ"] = row.organ

        return kind, entity

    return build()


def _analog_entity(entity_type: str) -> st.SearchStrategy[tuple[str, dict[str, Any]]]:
    """A service with no Ziffer of its own, charged analogously under § 6 Abs. 2 GOÄ."""
    return st.builds(
        lambda confidence, complexity: (
            "procedure",
            {"type": entity_type, "confidence": confidence, "complexity": complexity},
        ),
        confidence=CONFIDENCES,
        complexity=COMPLEXITIES,
    )


#: One documented service. Mapping rows are sampled *with replacement*, on purpose: documenting
#: the same service twice is what makes the uniqueness invariant a real test rather than a
#: tautology over a set the generator already deduplicated.
SERVICES = st.one_of(
    st.sampled_from(ROWS).flatmap(_entity),
    *([st.sampled_from(ANALOG_TYPES).flatmap(_analog_entity)] if ANALOG_TYPES else []),
)


# ------------------------------------------------------------------------------------------
# the region where a § 6 Abs. 2 ladder meets the exclusion table
# ------------------------------------------------------------------------------------------


def _analog_exclusion_rows() -> dict[str, tuple[MappingRow, ...]]:
    """Per Analogansatz entity type, the services that collide with one of its candidate targets.

    A candidate target is incompatible with another position when the exclusion table names the
    pair in either direction, or when the Zielleistung table makes one a component of the other.
    Both relations are read from `RULES`, which is loaded under the same
    `UnverifiedRulePolicy.WARN` the pipeline runs with — so these are the rules that actually
    constrain an invoice, not every row in the CSVs.

    Documenting one of these services alongside the analog one forces the § 6 Abs. 2 ladder to
    reckon with the exclusion table: the closest candidate may be unusable, and the engine has to
    either walk to a legal one or say that it cannot. **That used to be an open defect** — see the
    module docstring — and it is the region `analog_exclusion_requests()` now generates.

    Derived from the rule tables rather than written out, so a new analog candidate or a new
    exclusion widens it automatically instead of silently costing coverage.
    """
    targets: dict[str, set[str]] = {}
    for rule in RULES.analog_candidates:
        if CATALOG.has(rule.target_ziffer) and CATALOG.is_active(rule.target_ziffer):
            targets.setdefault(rule.source_entity_type, set()).add(rule.target_ziffer)

    pairs: list[tuple[str, str]] = [
        (rule.from_ziffer, rule.to_ziffer) for rule in RULES.exclusions
    ] + [(rule.parent_ziffer, rule.child_ziffer) for rule in RULES.zielleistung]

    rows: dict[str, tuple[MappingRow, ...]] = {}
    for entity_type, target_ziffern in targets.items():
        incompatible = {
            other
            for target in target_ziffern
            for left, right in pairs
            for other in ({right} if left == target else set())
            | ({left} if right == target else set())
        }
        matching = tuple(row for row in ROWS if row.ziffer in incompatible)
        if matching:
            rows[entity_type] = matching
    return rows


#: analog entity type -> the mapping rows whose service collides with one of its candidates.
ANALOG_EXCLUSION_ROWS: dict[str, tuple[MappingRow, ...]] = _analog_exclusion_rows()

#: The same region as `(kind, type)` pairs — what a request actually carries. Pinned by
#: `test_the_generated_space_is_worth_exploring` so the region cannot shrink unnoticed.
ANALOG_EXCLUSION_REGION: dict[str, frozenset[tuple[str, str]]] = {
    entity_type: frozenset((_kind(row), _service_type(row)) for row in rows)
    for entity_type, rows in ANALOG_EXCLUSION_ROWS.items()
}


def _place(extraction: dict[str, Any], kind: str, entity: dict[str, Any]) -> None:
    """Put one generated service into the list of the extraction it belongs in.

    The contract has room for exactly one consultation per encounter; a second drawn one is
    dropped rather than coerced into a procedure, which would document something that did not
    happen. Shared by both request strategies so they cannot disagree about placement.
    """
    if kind == "consultation":
        extraction.setdefault("consultation", entity)
    else:
        extraction[f"{kind}s"].append(entity)


@st.composite
def solve_requests(draw: Any, min_services: int = 1, max_services: int = 10) -> dict[str, Any]:
    """A `POST /api/v1/solve` body: 1-10 documented services and the circumstances around them.

    Returned as a plain JSON-shaped dict, not a model. Two reasons: `solve()` can then parse a
    fresh object per run, and a falsifying example prints as the request body a caller would have
    sent, which is what someone reproducing it needs.
    """
    services = draw(st.lists(SERVICES, min_size=min_services, max_size=max_services))

    extraction: dict[str, Any] = {
        "patient": {
            "age": draw(st.integers(min_value=0, max_value=130)),
            "sex": draw(SEXES),
            "setting": draw(SETTINGS),
        },
        "examinations": [],
        "procedures": [],
        "lab_tests": [],
    }
    for kind, entity in services:
        _place(extraction, kind, entity)

    # What a justification can name. A lab test is addressable as "labor" rather than by its
    # analyte, because that is the `entity_type` the bridge builds the act with — naming the
    # analyte would land in the "target unknown" branch, which the third option below covers
    # deliberately and this one must not cover by accident.
    documented_types = sorted(
        {entity["type"] if kind != "lab_test" else "labor" for kind, entity in services}
    )

    # A justification either names a service or covers the whole encounter (§ 5 Abs. 2 GOÄ). Both
    # reach the factor ladder differently, and a target that resolves to nothing is a third path
    # the engine has to refuse to apply rather than widen — so all three are generated.
    targets = st.one_of(
        st.just([]),
        st.just(["leistung_die_nicht_dokumentiert_wurde"]),
        # Guarded rather than assumed non-empty: `st.sampled_from([])` is an error, and a caller
        # asking for `min_services=0` should get an empty encounter, not an InvalidArgument.
        *([st.sampled_from(documented_types).map(lambda t: [t])] if documented_types else []),
    )
    extraction["justification_factors"] = draw(
        st.lists(
            st.fixed_dictionaries(
                {"reason": REASONS, "severity": SEVERITIES, "applies_to": targets}
            ),
            max_size=2,
        )
    )

    payload: dict[str, Any] = {"extraction": extraction}
    # `setting` on the envelope overrides `patient.setting`, and § 6a Minderung follows it. Drawn
    # separately so both ways of stating the same thing are exercised.
    if draw(st.booleans()):
        payload["setting"] = draw(SETTINGS)
    return payload


@st.composite
def analog_exclusion_requests(draw: Any) -> dict[str, Any]:
    """A request that puts a § 6 Abs. 2 ladder up against the exclusion table on purpose.

    One Analogansatz service, plus at least one documented service whose Ziffer is incompatible
    with one of that analog type's candidate targets, plus an ordinary drawn encounter around them
    so the properties are exercised against a realistic invoice rather than a two-line one.

    `solve_requests` reaches this region on its own — the filter that used to keep it out is gone —
    but only by chance, and the interesting combinations are a small corner of a wide space. This
    strategy makes them the *only* thing drawn, which is what turns
    `test_analog_positions_obey_the_same_hard_rules` into a test that reliably runs rather than one
    that occasionally happens to.
    """
    payload = draw(solve_requests(min_services=0, max_services=4))
    extraction = payload["extraction"]

    entity_type = draw(st.sampled_from(sorted(ANALOG_EXCLUSION_ROWS)))
    _kind_, analog_entity = draw(_analog_entity(entity_type))
    _place(extraction, _kind_, analog_entity)

    rows = ANALOG_EXCLUSION_ROWS[entity_type]
    conflicting = draw(
        st.lists(
            st.sampled_from(rows),
            min_size=1,
            max_size=len(rows),
            unique_by=lambda row: row.ziffer,
        )
    )
    for row in conflicting:
        kind, entity = draw(_entity(row))
        _place(extraction, kind, entity)

    return payload
