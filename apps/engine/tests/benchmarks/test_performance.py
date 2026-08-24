"""Three benchmarks, each with a soft and a hard threshold, over the paths that carry a request.

Run them — they are skipped by default, see `pytest.ini`:

    .venv/bin/python -m pytest tests/benchmarks --benchmark-only

Baselines, the machine they were measured on, and the threshold arithmetic are in
[`docs/performance_baselines.md`](../../../../docs/performance_baselines.md). The thresholds below
are the only place those numbers appear in code, and each is written as the baseline followed by the
multiplier so a reader can check the arithmetic without leaving the line.

## What these three are, and what they are not

They are the three costs a deployment actually pays, measured on real inputs:

1. **boot** — parsing the official GOÄ snapshot and the rule tables, once per process.
2. **a request** — `Pipeline.propose` on `case_001_knee`, exactly as `POST /api/v1/solve` calls it.
3. **persistence** — writing a proposal and reading it back, which is what an approval survives on.

They are not micro-benchmarks. Nothing here times a function in isolation with synthetic arguments:
`docs/performance_baseline.md` already established that the interesting costs are process spawns and
file parsing, not any single Python frame, and a micro-benchmark over the latter would be a number
that moves without meaning anything. Each of these three drives the real catalog, the real rule
tables and the real committed case.

## Why every one of them fights a cache

All three targets are memoised in production, which is correct for production and would make a
benchmark measure the memo:

- `load_catalog` and `load_rules` are `lru_cache`d, so the second call is a dict lookup. These
  benchmarks call `Catalog.load` and `RuleStore.load` — the uncached functions the cached wrappers
  delegate to — rather than clearing a process-wide cache other tests are holding.
- `Pipeline.propose` is content-addressed, and its key is the *facts*. Ten rounds on one case would
  be one solve and nine cache hits, i.e. a benchmark of `dict.get`. So the pipeline here is built
  with `cache_enabled=False`, the same reason and the same mechanism as `tests/property/conftest.py`.
- SQLAlchemy's identity map would serve the read-back from memory within a session.
  `ProposalStore.get_proposal` opens its own session per call, so the round trip really does reach
  the file — but the database is a file in `tmp_path` rather than the suite's `:memory:` default,
  because for in-memory SQLite the connection *is* the database and there would be nothing on the
  other side of the write to read back from.

## `pedantic`, not the plain call

`benchmark(fn)` calibrates: it works out how many iterations fit in a time budget and runs however
many rounds that implies. For targets in the tens of milliseconds that is both slow and unnecessary.
`benchmark.pedantic(rounds=10, iterations=1)` runs exactly ten timed rounds and reports their
median, which is what the baselines document. `warmup_rounds=1` absorbs the first-call costs that
are not what is being measured — import-time lazy initialisation, a cold page cache on the catalog
JSON, the first `souffle` spawn. Those are real, and they are not a regression: the measured spread
in the doc shows the first round of a load running ~2x the median and every subsequent one landing
within 5%.

The median, not the mean or the min. The mean follows an outlier produced by whatever else the
machine was doing; the min reports the luckiest round, which flatters a regression that made the
typical case slower. The median is the number a request actually experiences.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Iterator

import pytest

from app.catalog.catalog_loader import Catalog
from app.config import CASES_DIR, RULES_DATA_DIR, Settings
from app.db.session import Database
from app.rules.rule_store import RuleStore
from app.schemas import SolveRequest
from app.services.pipeline import Pipeline
from app.services.proposal_store import ProposalStore
from tests.benchmarks.conftest import check_thresholds
from tests.conftest import _require_or_skip
from tests.factories import make_proposal

#: Every benchmark reports the median of this many timed rounds, after one untimed warm-up round.
ROUNDS = 10
WARMUP_ROUNDS = 1

#: The case the request benchmark solves. `case_001_knee` rather than one of the eight because it is
#: the most ordinary: a consultation, two examinations and a puncture, 8 candidate Ziffern, one
#: mutual-conflict pair and 5 invoice lines. `case_008_complex_polytrauma` would measure the tail
#: and `case_003_dermatology` has nothing left to arbitrate — neither is what a typical request
#: costs. It is also the case `docs/performance_baseline.md` profiled stage by stage, so a
#: regression here can be attributed to a stage without new measurement.
BENCHMARK_CASE = "case_001_knee"


# ------------------------------------------------------------------------------------------
# fixtures
# ------------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def uncached_pipeline(settings: Settings, catalog, rules) -> Pipeline:
    """A pipeline whose result cache is off. See the module docstring.

    Module-scoped: it holds no per-solve state once the cache is off, and rebuilding it per test
    would re-pay the Soufflé availability probe for nothing.
    """
    pipeline = Pipeline(settings.model_copy(update={"cache_enabled": False}), catalog, rules)
    if not pipeline.souffle.available():
        _require_or_skip(pipeline.settings)
    return pipeline


@pytest.fixture
def loop() -> Iterator[asyncio.AbstractEventLoop]:
    """One event loop for the whole benchmark, driven by hand.

    `benchmark.pedantic` calls a *synchronous* target, so the async store has to be driven from
    inside it — and every round has to use the same loop, because the SQLAlchemy engine binds its
    connection pool to the loop that first touched it. A fresh `asyncio.run` per round would build
    and tear down a loop inside the timed region and measure that instead.

    Not `pytest-asyncio`'s loop: `asyncio_mode = auto` gives one to `async def` tests, and this test
    is deliberately not one.
    """
    loop = asyncio.new_event_loop()
    try:
        yield loop
    finally:
        loop.close()


@pytest.fixture
def file_backed_store(
    loop: asyncio.AbstractEventLoop, tmp_path: Path
) -> Iterator[ProposalStore]:
    """A `ProposalStore` over a SQLite *file*, created and disposed on `loop`.

    A file rather than the suite's `:memory:` default for the reason `tests/test_db_persistence.py`
    gives: for in-memory SQLite the connection is the database, so a write and a read-back that
    share nothing would have nothing to share.
    """
    database = Database(
        Settings(
            app_env="development",
            database_url=f"sqlite+aiosqlite:///{tmp_path / 'benchmark.db'}",
            database_auto_create=True,
        )
    )
    loop.run_until_complete(database.create_all())
    try:
        yield ProposalStore(database)
    finally:
        loop.run_until_complete(database.dispose())


# ------------------------------------------------------------------------------------------
# 1. boot — parsing the catalog and the rule tables
# ------------------------------------------------------------------------------------------


def test_rule_store_load_time(benchmark) -> None:
    """Parsing the GOÄ snapshot JSON and the rule CSVs, which is what a process pays at boot.

    Both, not either. They are one cost in practice — no process serves a request having loaded one
    and not the other — and `docs/performance_baseline.md` reports them as a single
    "catalog + rules load" line, so measuring them together is what makes this benchmark comparable
    to the profile that motivated it. The split is recorded in `extra_info` all the same, because a
    regression in the 2192-Ziffer JSON parse and a regression in the 892-rule CSV parse have nothing
    to do with each other and the artefact should not force a bisect to tell them apart.

    `Catalog.load` and `RuleStore.load` rather than the `lru_cache`d `load_catalog` / `load_rules`:
    the cached pair would report a dict lookup from round two onward, and `cache_clear()` would
    evict the copy the session fixtures are holding for every other test in the suite.
    """

    def load_catalog_and_rules() -> tuple[Catalog, RuleStore]:
        return Catalog.load(), RuleStore.load(RULES_DATA_DIR)

    catalog, rules = benchmark.pedantic(
        load_catalog_and_rules, rounds=ROUNDS, warmup_rounds=WARMUP_ROUNDS, iterations=1
    )

    # A load that parsed nothing would be extremely fast and would pass any threshold, so the
    # benchmark asserts it loaded the real thing before it asserts on the clock.
    assert len(catalog.ziffern) > 2000, "the official snapshot has 2192 Ziffern"
    assert rules.constraint_rule_count() > 0, "a rule store with no constraints parsed nothing"
    benchmark.extra_info["ziffern"] = len(catalog.ziffern)
    benchmark.extra_info["constraint_rules"] = rules.constraint_rule_count()

    check_thresholds(
        benchmark,
        what="catalog + rule-table load (cold, per process)",
        baseline_ms=23.0,
        soft_ms=28.0,   # 23.0 x 1.2, rounded up
        hard_ms=46.0,   # 23.0 x 2.0
    )


# ------------------------------------------------------------------------------------------
# 2. a request — bridge, Soufflé, Clingo, verification, validation, receipt
# ------------------------------------------------------------------------------------------


def test_single_case_solve_time(benchmark, uncached_pipeline: Pipeline) -> None:
    """One realistic request end to end: `Pipeline.propose` on `case_001_knee`.

    `propose`, not `run` or `run_symbolic`, because `propose` is what the endpoint calls — it is the
    one that also builds the receipt hash and the rule-coverage report, and those are ~12% of a
    request per `docs/performance_baseline.md`. Benchmarking the symbolic core alone would leave
    that 12% unguarded.

    A fresh `SolveRequest` is parsed per round, in `setup`, so parsing is outside the timed region
    and — the load-bearing half — no two rounds share an extraction. `propose` assigns
    `patient.setting` and the extraction validator fills in entity ids, so handing one object to ten
    rounds would benchmark a mutated input from round two onward.
    """
    payload = json.loads(
        (CASES_DIR / BENCHMARK_CASE / "input.json").read_text(encoding="utf-8")
    )

    def setup() -> tuple[tuple[Any, ...], dict[str, Any]]:
        return (SolveRequest.model_validate({"extraction": payload}),), {}

    def solve(request: SolveRequest):
        return uncached_pipeline.propose(
            request.extraction, setting=request.setting, case_id=request.case_id
        )

    proposal = benchmark.pedantic(
        solve, setup=setup, rounds=ROUNDS, warmup_rounds=WARMUP_ROUNDS
    )

    # A solve that produced no invoice is not a fast solve, and an UNSATISFIABLE run would be much
    # cheaper than a real one — so the timing only means something once the result is checked.
    assert proposal.solver_status == "SAT", proposal.solver_status
    assert proposal.solver_result.coding.proposed_codes, "no invoice lines: nothing was solved"
    assert not proposal.cached, "the cache is supposed to be off for this benchmark"
    benchmark.extra_info["case"] = BENCHMARK_CASE
    benchmark.extra_info["invoice_lines"] = len(proposal.solver_result.coding.proposed_codes)

    check_thresholds(
        benchmark,
        what=f"Pipeline.propose on {BENCHMARK_CASE} (cache off)",
        baseline_ms=76.0,
        soft_ms=92.0,   # 76.0 x 1.2, rounded up
        hard_ms=152.0,  # 76.0 x 2.0
    )


# ------------------------------------------------------------------------------------------
# 3. persistence — the write an approval depends on, and the read back
# ------------------------------------------------------------------------------------------


def test_proposal_db_write_read(
    benchmark, loop: asyncio.AbstractEventLoop, file_backed_store: ProposalStore
) -> None:
    """`create_proposal` then `get_proposal`: one full round trip through the ORM and the file.

    Both halves in one benchmark because neither is meaningful alone — the write is what an
    approval survives on and the read is what a reviewer waits for, and they share the JSON
    serialisation of a whole `CodingResponse`, which is where the cost actually is. Splitting them
    would produce two numbers that move together and neither of which is a request.

    The proposal is built in `setup`, so `make_proposal`'s uuid generation and Pydantic construction
    are outside the timed region. Each round therefore inserts a *new* row, which is the honest
    shape: an `INSERT` into a table that already has rows, not the same row overwritten ten times.

    SQLite, because that is the dialect a laptop and this benchmark have. Postgres over a network
    is a different number entirely and this threshold would say nothing about it — the doc records
    that limitation rather than pretending the gate covers production.
    """

    def setup() -> tuple[tuple[Any, ...], dict[str, Any]]:
        return (make_proposal(),), {}

    async def round_trip(proposal):
        created = await file_backed_store.create_proposal(proposal)
        return await file_backed_store.get_proposal(created.proposal_id, record_view=True)

    def write_then_read(proposal):
        return loop.run_until_complete(round_trip(proposal))

    read_back = benchmark.pedantic(
        write_then_read, setup=setup, rounds=ROUNDS, warmup_rounds=WARMUP_ROUNDS
    )

    # The read has to have returned the record that was written, or this is a benchmark of an
    # exception path that happened not to raise.
    assert read_back.solver_result.coding.proposed_codes, "the round trip lost the invoice"
    assert read_back.receipt_hash, "the round trip lost the receipt hash"
    benchmark.extra_info["dialect"] = "sqlite+aiosqlite (file)"

    check_thresholds(
        benchmark,
        what="ProposalStore create + read back (SQLite file)",
        baseline_ms=9.4,
        soft_ms=11.3,  # 9.4 x 1.2, rounded up
        hard_ms=19.0,  # 9.4 x 2.0, rounded up
    )
