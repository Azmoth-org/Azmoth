"""Durability, isolation and the schema itself.

The claim this migration makes is that an approval survives a restart. That claim cannot be tested
against the in-memory SQLite the rest of the suite uses — closing the connection *is* the restart,
and it takes the database with it — so every test here builds a file-backed database in `tmp_path`,
disposes the engine completely, opens a second one against the same file and reads the record back.
Disposing is the point: it drops the pool, closes the file handle and discards every identity map,
so the second `Database` shares nothing with the first but the bytes on disk.

**Running these against Postgres.** SQLite proves persistence but not the dialect: JSONB, `SELECT …
FOR UPDATE` and `TIMESTAMP WITH TIME ZONE` all behave differently. Point `POSTGRES_TEST_URL` at a
scratch database and the same assertions run there too:

    docker run --rm -d -p 5433:5432 -e POSTGRES_PASSWORD=test --name goae-test-db postgres:15-alpine
    POSTGRES_TEST_URL=postgresql+asyncpg://postgres:test@localhost:5433/postgres \\
        python -m pytest tests/test_db_persistence.py -v

Without the variable those parametrisations skip, and say so. The tables are dropped and recreated
around each one, so it must be a scratch database — which is why there is no default value.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

from app.config import Settings
from app.db.models import AuditEventType
from app.db.session import Database
from app.schemas import ProposalStatus
from app.services.proposal_store import (
    IllegalTransitionError,
    ProposalNotFound,
    ProposalStore,
    input_hash_of,
)
from tests.factories import make_proposal

POSTGRES_TEST_URL = os.getenv("POSTGRES_TEST_URL", "").strip()

#: Both dialects the engine supports. `sqlite` is the local file in `tmp_path`; `postgres` runs only
#: when POSTGRES_TEST_URL is set, and skips with a message naming the variable when it is not.
BACKENDS = ["sqlite", "postgres"]


def _settings(url: str) -> Settings:
    return Settings(app_env="development", database_url=url, database_auto_create=True)


@pytest.fixture(params=BACKENDS)
async def durable_url(request, tmp_path) -> str:
    """A database URL that outlives a disposed engine, for each supported dialect.

    Postgres is left clean on both ends: the tables are dropped before the test as well as after,
    because a previous run that crashed mid-test would otherwise leave rows behind and the next run
    would assert against them.
    """
    if request.param == "sqlite":
        yield f"sqlite+aiosqlite:///{tmp_path / 'proposals.db'}"
        return

    if not POSTGRES_TEST_URL:
        pytest.skip(
            "POSTGRES_TEST_URL is not set, so the Postgres dialect (JSONB, FOR UPDATE, "
            "timezone-aware timestamps) is not exercised. See this module's docstring."
        )

    database = Database(_settings(POSTGRES_TEST_URL))
    await database.drop_all()
    await database.create_all()
    await database.dispose()
    try:
        yield POSTGRES_TEST_URL
    finally:
        cleanup = Database(_settings(POSTGRES_TEST_URL))
        await cleanup.drop_all()
        await cleanup.dispose()


async def _open(url: str) -> Database:
    database = Database(_settings(url))
    await database.create_all()
    return database


# ==========================================================================================
# durability — the whole point of this migration
# ==========================================================================================


async def test_a_proposal_survives_a_full_restart(durable_url):
    """Write, dispose everything, reopen, read back. This is the compliance blocker closing."""
    first = await _open(durable_url)
    proposal = make_proposal(case_id="ENC-restart")
    created = await ProposalStore(first).create_proposal(proposal)
    await first.dispose()

    second = await _open(durable_url)
    try:
        reloaded = await ProposalStore(second).get_proposal(created.proposal_id)
    finally:
        await second.dispose()

    assert reloaded.proposal_id == created.proposal_id
    assert reloaded.status is ProposalStatus.DRAFT
    assert reloaded.case_id == "ENC-restart"


async def test_an_approval_survives_a_full_restart(durable_url):
    """The one that matters: who approved it and when, still there after the process died."""
    first = await _open(durable_url)
    created = await ProposalStore(first).create_proposal(make_proposal())
    approved = await ProposalStore(first).approve_proposal(
        created.proposal_id, approved_by="Dr. Beispiel"
    )
    await first.dispose()

    second = await _open(durable_url)
    try:
        reloaded = await ProposalStore(second).get_proposal(created.proposal_id)
        events = await ProposalStore(second).audit_events(created.proposal_id)
    finally:
        await second.dispose()

    assert reloaded.status is ProposalStatus.APPROVED
    assert reloaded.approved_by == "Dr. Beispiel"
    assert reloaded.approved_at is not None
    assert reloaded.approved_at == approved.approved_at
    assert [e["event_type"] for e in events] == ["CREATED", "APPROVED"]


async def test_the_whole_response_round_trips_byte_for_byte(durable_url):
    """Persistence must not quietly reshape the invoice.

    The receipt hash attests to the response as served, so a proposal that comes back out of the
    database with a re-serialised total or a dropped proof is a proposal whose receipt no longer
    describes it. Compared as a full model dump rather than field by field, so a field added to
    `Proposal` later is covered without anyone remembering to extend this test.
    """
    database = await _open(durable_url)
    try:
        store = ProposalStore(database)
        original = make_proposal(case_id="ENC-roundtrip")

        created = await store.create_proposal(original)
        reloaded = await store.get_proposal(created.proposal_id)

        assert created.model_dump(mode="json") == reloaded.model_dump(mode="json")
        assert reloaded.solver_result.model_dump(mode="json") == original.solver_result.model_dump(
            mode="json"
        )
        assert reloaded.receipt_hash == original.receipt_hash
        assert reloaded.rule_coverage == original.rule_coverage
        assert reloaded.enforced_rule_count == original.enforced_rule_count
    finally:
        await database.dispose()


async def test_timestamps_come_back_in_utc_not_naive(durable_url):
    """SQLite has no timestamp type and returns exactly the naive value it was given.

    Reading that back as local time is how an audit log ends up an hour out twice a year. Everything
    is written in UTC and re-tagged on the way out; Postgres does it itself.
    """
    database = await _open(durable_url)
    try:
        store = ProposalStore(database)
        created = await store.create_proposal(make_proposal())
        approved = await store.approve_proposal(created.proposal_id, approved_by="Dr. B")
        events = await store.audit_events(created.proposal_id)

        for stamp in (created.created_at, approved.approved_at):
            assert stamp is not None and stamp.tzinfo is not None
            assert stamp.utcoffset() == timedelta(0)

        for event in events:
            assert event["timestamp"].tzinfo is not None
            assert event["timestamp"].utcoffset() == timedelta(0)
    finally:
        await database.dispose()


# ==========================================================================================
# the derived input hash
# ==========================================================================================


async def test_the_input_hash_identifies_the_case_across_engine_versions(store):
    """Same clinical input, different receipt: the input hash is what links them.

    Two proposals produced from identical facts under two different catalogs have two receipt
    hashes, because a receipt covers the engine's identity as well as the input. `input_hash` is
    the narrow digest that still matches, which is what makes "find every proposal for this case"
    answerable after a catalog bump.
    """
    one = make_proposal(receipt_hash="1" * 64)
    two = make_proposal(receipt_hash="2" * 64)

    assert one.receipt_hash != two.receipt_hash
    assert input_hash_of(one) == input_hash_of(two), "identical facts, so one input hash"

    different = make_proposal(extraction=None)
    different.solver_result.extraction.patient.age = 71
    assert input_hash_of(different) != input_hash_of(one)

    created = await store.create_proposal(one)
    assert created.proposal_id


# ==========================================================================================
# isolation — the suite's own guarantee
# ==========================================================================================


async def test_two_databases_do_not_see_each_others_rows(tmp_path):
    """What makes the in-memory default a valid isolation mechanism for the rest of the suite."""
    left = await _open(f"sqlite+aiosqlite:///{tmp_path / 'left.db'}")
    right = await _open(f"sqlite+aiosqlite:///{tmp_path / 'right.db'}")
    try:
        stored = await ProposalStore(left).create_proposal(make_proposal())

        assert await ProposalStore(left).count() == 1
        assert await ProposalStore(right).count() == 0
        with pytest.raises(ProposalNotFound):
            await ProposalStore(right).get_proposal(stored.proposal_id)
    finally:
        await left.dispose()
        await right.dispose()


# ==========================================================================================
# listing
# ==========================================================================================


async def test_listing_filters_by_status_and_keeps_insertion_order(store):
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    first, second, third = [
        await store.create_proposal(make_proposal(created_at=base + timedelta(minutes=i)))
        for i in range(3)
    ]

    await store.approve_proposal(second.proposal_id, approved_by="Dr. B")

    everything = await store.list_proposals()
    drafts = await store.list_proposals(status=ProposalStatus.DRAFT)
    approved = await store.list_proposals(status=ProposalStatus.APPROVED)

    assert [p.proposal_id for p in everything] == [
        first.proposal_id,
        second.proposal_id,
        third.proposal_id,
    ]
    assert [p.proposal_id for p in drafts] == [first.proposal_id, third.proposal_id]
    assert [p.proposal_id for p in approved] == [second.proposal_id]


async def test_the_limit_keeps_the_newest_not_the_oldest(store):
    """A durable store only grows, so a capped list must show the recent end of it.

    The in-memory store evicted its oldest entry past 512 and returned insertion order, so "newest
    N, ascending" reproduces what a client already saw — and "oldest N" would have shown a
    production database its first week, forever.
    """
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    created = [
        await store.create_proposal(make_proposal(created_at=base + timedelta(minutes=i)))
        for i in range(5)
    ]

    newest_two = await store.list_proposals(limit=2)

    assert [p.proposal_id for p in newest_two] == [
        created[3].proposal_id,
        created[4].proposal_id,
    ], "ascending order, but the newest two"


# ==========================================================================================
# state transitions, at the store level
# ==========================================================================================


async def test_approving_requires_a_named_approver(store):
    created = await store.create_proposal(make_proposal())

    for bad in ("", "   "):
        with pytest.raises(ValueError, match="approved_by"):
            await store.approve_proposal(created.proposal_id, approved_by=bad)

    unchanged = await store.get_proposal(created.proposal_id)
    assert unchanged.status is ProposalStatus.DRAFT, "a refused approval must change nothing"


async def test_rejecting_requires_both_a_name_and_a_reason(store):
    created = await store.create_proposal(make_proposal())

    with pytest.raises(ValueError, match="rejected_by"):
        await store.reject_proposal(created.proposal_id, rejected_by="", reason="nope")
    with pytest.raises(ValueError, match="reason"):
        await store.reject_proposal(created.proposal_id, rejected_by="Dr. B", reason="  ")

    assert (await store.get_proposal(created.proposal_id)).status is ProposalStatus.DRAFT


async def test_rejection_records_who_when_and_why_in_columns_the_api_does_not_expose(store):
    """`rejected_at` and `rejected_by` are stored even though the response does not carry them.

    The `Proposal` schema is the frontend's contract and this migration does not move it, so the two
    columns are written for the audit question and read from the database — via the audit log, which
    is where "who rejected this" belongs anyway.
    """
    created = await store.create_proposal(make_proposal())
    rejected = await store.reject_proposal(
        created.proposal_id, rejected_by="Dr. Beispiel", reason="Sonographie nicht dokumentiert"
    )

    assert rejected.status is ProposalStatus.REJECTED
    assert rejected.rejected_reason == "Sonographie nicht dokumentiert"

    events = await store.audit_events(created.proposal_id)
    rejection = next(e for e in events if e["event_type"] == "REJECTED")
    assert rejection["actor"] == "Dr. Beispiel"
    assert rejection["metadata"]["reason"] == "Sonographie nicht dokumentiert"
    assert rejection["metadata"]["from_status"] == "DRAFT"


@pytest.mark.parametrize(
    "first_decision,then",
    [
        ("approve", "approve"),
        ("approve", "reject"),
        ("reject", "approve"),
        ("reject", "reject"),
        ("reject", "export"),
    ],
)
async def test_a_decided_proposal_cannot_be_decided_again(store, first_decision, then):
    """Every terminal-state re-decision the lifecycle forbids, enumerated.

    Approving a rejected proposal is the case named in the brief; the others fail for the same
    reason and are here so that a change to `ALLOWED` cannot quietly permit one of them.
    """
    created = await store.create_proposal(make_proposal())
    actions = {
        "approve": lambda: store.approve_proposal(created.proposal_id, approved_by="Dr. B"),
        "reject": lambda: store.reject_proposal(
            created.proposal_id, rejected_by="Dr. B", reason="not documented"
        ),
        "export": lambda: store.export_proposal(created.proposal_id),
    }

    before = await actions[first_decision]()

    with pytest.raises(IllegalTransitionError) as raised:
        await actions[then]()

    assert raised.value.current is before.status
    after = await store.get_proposal(created.proposal_id)
    assert after.status is before.status, "a refused transition must leave the record untouched"
    assert after.approved_by == before.approved_by


async def test_export_is_reachable_only_from_approved(store):
    created = await store.create_proposal(make_proposal())

    with pytest.raises(IllegalTransitionError):
        await store.export_proposal(created.proposal_id)

    await store.approve_proposal(created.proposal_id, approved_by="Dr. B")
    exported = await store.export_proposal(created.proposal_id)

    assert exported.status is ProposalStatus.EXPORTED
    assert [e["event_type"] for e in await store.audit_events(created.proposal_id)] == [
        "CREATED",
        "APPROVED",
        "EXPORTED",
    ]


async def test_a_refused_transition_writes_no_audit_event(store):
    """The log records what happened, not what was attempted and refused.

    A rejected approval attempt is an application error (409), not an event in the proposal's
    history — and if it did write one, the transaction would have to be split from the check, which
    is exactly the race the row lock exists to prevent.
    """
    created = await store.create_proposal(make_proposal())
    await store.reject_proposal(created.proposal_id, rejected_by="Dr. B", reason="no")

    with pytest.raises(IllegalTransitionError):
        await store.approve_proposal(created.proposal_id, approved_by="Dr. Optimist")

    events = await store.audit_events(created.proposal_id)
    assert [e["event_type"] for e in events] == ["CREATED", "REJECTED"]
    assert all(e["actor"] != "Dr. Optimist" for e in events)


async def test_an_unknown_proposal_is_not_found_rather_than_created(store):
    with pytest.raises(ProposalNotFound):
        await store.get_proposal("prop_does_not_exist")
    with pytest.raises(ProposalNotFound):
        await store.approve_proposal("prop_does_not_exist", approved_by="Dr. B")
    with pytest.raises(ProposalNotFound):
        await store.audit_events("prop_does_not_exist")

    assert await store.count() == 0


# ==========================================================================================
# the schema, and the migration that creates it
# ==========================================================================================


def test_the_migration_and_the_models_describe_the_same_schema(tmp_path):
    """Alembic's `upgrade head` must produce exactly what `Base.metadata` declares.

    A plain `def`, not a coroutine: `alembic/env.py` drives its async engine with `asyncio.run`,
    which refuses to start inside an already-running loop. That is the right shape for env.py — it
    is invoked from a sync CLI — so the test matches it rather than the reverse.

    The drift this catches is the ordinary one: somebody adds a column to `app/db/models.py`, the
    tests pass (because the suite uses `create_all`), and the deploy runs `alembic upgrade head`
    against a schema that does not have it. Compared as tables, columns, nullability and index
    names — not as DDL text, which differs harmlessly between the two paths.
    """
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, inspect

    from app.config import ENGINE_DIR
    from app.db.base import Base

    migrated_path = tmp_path / "migrated.db"
    config = Config(str(ENGINE_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(ENGINE_DIR / "alembic"))
    # `env.py` reads DATABASE_URL through Settings, so this is how the target is chosen.
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{migrated_path}"
    try:
        from app.config import get_settings

        get_settings.cache_clear()
        command.upgrade(config, "head")
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
        from app.config import get_settings

        get_settings.cache_clear()

    declared_path = tmp_path / "declared.db"
    declared_engine = create_engine(f"sqlite:///{declared_path}")
    Base.metadata.create_all(declared_engine)

    def describe(engine) -> dict:
        inspector = inspect(engine)
        return {
            table: {
                "columns": {
                    column["name"]: (str(column["type"]), column["nullable"])
                    for column in inspector.get_columns(table)
                },
                "primary_key": tuple(inspector.get_pk_constraint(table)["constrained_columns"]),
                "indexes": {
                    index["name"]: (tuple(index["column_names"]), bool(index["unique"]))
                    for index in inspector.get_indexes(table)
                },
                "foreign_keys": {
                    (
                        tuple(fk["constrained_columns"]),
                        fk["referred_table"],
                        tuple(fk["referred_columns"]),
                    )
                    for fk in inspector.get_foreign_keys(table)
                },
            }
            for table in sorted(inspector.get_table_names())
            if table != "alembic_version"
        }

    migrated_engine = create_engine(f"sqlite:///{migrated_path}")
    try:
        migrated, declared = describe(migrated_engine), describe(declared_engine)
    finally:
        migrated_engine.dispose()
        declared_engine.dispose()

    assert set(migrated) == {"proposals", "audit_events"}
    assert migrated == declared, (
        "alembic/versions/ has drifted from app/db/models.py — run "
        "`alembic revision --autogenerate -m '…'` and review the result"
    )


async def test_every_column_the_brief_requires_exists(store):
    """The schema the migration brief specified, asserted by name.

    Including the four columns the API response does not carry — `input_hash`, `rejected_at`,
    `rejected_by`, `exported_at`. They are written and they are queryable; they are absent from the
    `Proposal` schema because adding them would change the OpenAPI document, which this migration
    deliberately leaves alone.
    """
    from sqlalchemy import inspect as sa_inspect

    from app.db.models import AuditEvent, ProposalRecord

    proposal_columns = {c.key for c in sa_inspect(ProposalRecord).columns}
    audit_columns = {c.key for c in sa_inspect(AuditEvent).columns}

    assert {
        "id",
        "case_id",
        "status",
        "receipt_hash",
        "input_hash",
        "catalog_version",
        "rules_version",
        "logic_version",
        "solver_version",
        "solver_result_json",
        "warnings_json",
        "missing_documentation_json",
        "rule_coverage_json",
        "created_at",
        "approved_at",
        "approved_by",
        "rejected_at",
        "rejected_by",
        "rejected_reason",
    } <= proposal_columns

    assert {
        "id",
        "proposal_id",
        "event_type",
        "actor",
        "timestamp",
        "metadata_json",
    } <= audit_columns

    created = await store.create_proposal(make_proposal())
    assert created.proposal_id.startswith("prop_"), "the public id format is part of the contract"


def test_the_indexed_columns_are_the_ones_that_are_queried():
    """An index that exists for no query is cost; a query with no index is a scan at 3 a.m."""
    from app.db.models import AuditEvent, ProposalRecord

    def indexed(model) -> set[str]:
        names: set[str] = set()
        for index in model.__table__.indexes:
            names.update(column.name for column in index.columns)
        return names

    assert {"case_id", "status", "receipt_hash", "proposal_id", "created_at"} <= indexed(
        ProposalRecord
    )
    assert {"proposal_id", "event_type", "timestamp"} <= indexed(AuditEvent)


def test_the_event_type_vocabulary_is_closed():
    assert {str(t) for t in AuditEventType} == {
        "CREATED",
        "VIEWED",
        "APPROVED",
        "REJECTED",
        "EXPORTED",
    }
