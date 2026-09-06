"""Recovering a database whose schema arrived without a migration.

This file exists because of one production incident, and each test here is a step of it.

`DATABASE_AUTO_CREATE` defaults to true, and `init_models` used to refuse it only under
`APP_ENV=production`. A laptop pointed at the deployed Neon `DATABASE_URL` therefore ran
`Base.metadata.create_all` against it. `create_all` is `CREATE TABLE IF NOT EXISTS` over the whole
of `app/db/models.py`: it left every table the deployment already had, created the two that
migration `0010` had not yet added — `organization_billing` and `billing_invoices` — and never
touched `alembic_version`, which it has never heard of. The next deploy ran `alembic upgrade head`
and died on `DuplicateTableError: relation "organization_billing" already exists`.

Three things had to be true for that to be over, and this file asserts each of them:

    the mistake cannot be made again       `init_models` refuses create_all on Postgres
    the damaged databases can migrate      `0010` creates only what is absent
    the diagnosis is not guesswork         `--diagnose` tells stamping from repairing

The third matters more than it looks. The obvious fix for "relation already exists" is `alembic
stamp head`, and here that would have been wrong: `api_usage_logs.invoices_processed` was still
missing, so stamping would have declared the database migrated while a column an invoice is built
from did not exist — a silent failure, discovered by the first billing run rather than by the
deploy.

SQLite throughout. The dialect is not what is under test — the order of "does it exist" against
"create it" is — and every check the fix relies on (`get_table_names`, `get_columns`,
`get_indexes`) is SQLAlchemy's dialect-independent inspection API. The Postgres run in
`tests/test_db_persistence.py` covers the dialect itself.
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from app.config import ENGINE_DIR, Settings, get_settings
from app.db.session import Database, SchemaNotMigrated, init_models

#: The revision the deployed database was stamped with when the mistake was made.
BEFORE = "0009_api_usage_logs"

#: The revision that then failed, and the objects it builds.
BILLING = "0010_subscriptions_and_invoices"


def _config() -> Config:
    config = Config(str(ENGINE_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(ENGINE_DIR / "alembic"))
    return config


class _target:
    """Point `DATABASE_URL` at `path` for the duration of the block.

    A context manager and not a fixture because `alembic/env.py` reads the URL through
    `get_settings()`, whose cache has to be cleared on the way in *and* on the way out — leaking a
    scratch path into the rest of the suite would be a much more confusing failure than anything
    tested here.
    """

    def __init__(self, path: Path) -> None:
        self.url = f"sqlite+aiosqlite:///{path}"

    def __enter__(self) -> str:
        self._previous = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = self.url
        get_settings.cache_clear()
        return self.url

    def __exit__(self, *_exc) -> None:
        if self._previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = self._previous
        get_settings.cache_clear()


def _damaged(path: Path) -> None:
    """Rebuild the exact state the deployed database was found in.

    Migrate to `0009`, then run `create_all` over it — which is what the laptop did. Not a
    hand-written `CREATE TABLE`: the point is that this state is reachable by an ordinary mistake,
    and a fixture that forged it by hand could drift from what `create_all` really produces.
    """
    with _target(path):
        command.upgrade(_config(), BEFORE)
        database = Database(
            Settings(app_env="development", database_url=f"sqlite+aiosqlite:///{path}")
        )
        asyncio.run(database.create_all())
        asyncio.run(database.dispose())


def _tables(path: Path) -> set[str]:
    connection = sqlite3.connect(path)
    try:
        return {
            row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    finally:
        connection.close()


def _columns(path: Path, table: str) -> set[str]:
    connection = sqlite3.connect(path)
    try:
        return {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
    finally:
        connection.close()


def _stamp(path: Path) -> str | None:
    connection = sqlite3.connect(path)
    try:
        rows = connection.execute("SELECT version_num FROM alembic_version").fetchall()
        return rows[0][0] if rows else None
    finally:
        connection.close()


# ==============================================================================================
# the mistake
# ==============================================================================================


def test_the_incident_reproduces_at_all(tmp_path):
    """The premise of every other test here: `create_all` really does leave this exact mess.

    Worth asserting rather than assuming, because the shape of the mess is what the fix is built
    around. Two tables present, one column absent, and a stamp that still reads `0009` — if
    `create_all` had instead added the missing column, or updated `alembic_version`, the repair in
    `0010` would be aimed at the wrong thing.
    """
    database = tmp_path / "neon.db"
    _damaged(database)

    assert _stamp(database) == BEFORE, "create_all must not have touched alembic_version"
    assert "organization_billing" in _tables(database)
    assert "billing_invoices" in _tables(database)
    assert "invoices_processed" not in _columns(database, "api_usage_logs"), (
        "create_all skips a table that already exists, so it cannot add a column to one — "
        "which is precisely why stamping would have been the wrong repair"
    )


# ==============================================================================================
# it cannot be made again
# ==============================================================================================


def test_init_models_refuses_create_all_against_postgres_outside_production():
    """The guard that closes the hole, tested at the setting that was actually in force.

    `APP_ENV=development` — the default, and what the laptop had. The old guard looked only at
    `APP_ENV` and let this through.
    """
    settings = Settings(
        app_env="development",
        database_url="postgresql+asyncpg://user:pw@ep-x.eu-central-1.aws.neon.tech/azmoth",
        database_auto_create=True,
    )
    with pytest.raises(SchemaNotMigrated) as raised:
        asyncio.run(init_models(Database(settings)))

    message = str(raised.value)
    assert "DATABASE_AUTO_CREATE" in message
    assert "alembic_version" in message
    assert "pw" not in message, "the refusal goes to a deploy log; it must not carry the password"


def test_init_models_still_creates_a_local_sqlite_schema(tmp_path):
    """The guard is on the database, not on auto-create — a laptop's own file is untouched.

    Without this the fix would have been a regression: `pytest` and a bare `uvicorn app.main:app`
    both rely on getting their tables without a migration step.
    """
    settings = Settings(
        app_env="development",
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'local.db'}",
        database_auto_create=True,
    )
    database = Database(settings)
    try:
        asyncio.run(init_models(database))
    finally:
        asyncio.run(database.dispose())

    assert "organization_billing" in _tables(tmp_path / "local.db")


def test_init_models_leaves_postgres_alone_when_auto_create_is_off():
    """What every compose file sets. It must not have become an error along with the true case."""
    settings = Settings(
        app_env="development",
        database_url="postgresql+asyncpg://user:pw@ep-x.eu-central-1.aws.neon.tech/azmoth",
        database_auto_create=False,
    )
    # No connection is opened: the function returns before touching the database, which is what
    # makes it safe to call here against a host that does not exist.
    asyncio.run(init_models(Database(settings)))


# ==============================================================================================
# the damaged databases can migrate
# ==============================================================================================


def test_upgrade_head_recovers_a_database_that_create_all_got_to_first(tmp_path):
    """The failing deploy, now succeeding. This is the test the incident was about."""
    database = tmp_path / "neon.db"
    _damaged(database)

    with _target(database):
        command.upgrade(_config(), "head")  # raised DuplicateTableError before this fix

    assert _stamp(database) == "0011_retention_purge"
    assert "invoices_processed" in _columns(database, "api_usage_logs"), (
        "the whole reason not to stamp: the column 0010 adds must exist afterwards"
    )


def test_the_recovered_schema_is_what_the_models_declare(tmp_path):
    """Recovering must not merely stop failing — it must land on the same schema as a clean run.

    A guarded migration is easy to get subtly wrong: skip the table and you skip its indexes with
    it, and the database then has `organization_billing` without the unique index on
    `organization_id` that makes get-or-create safe under two simultaneous first audits. Compared
    against `Base.metadata` for the same reason
    `test_the_migration_and_the_models_describe_the_same_schema` does.
    """
    from sqlalchemy import create_engine, inspect

    from app.db.base import Base

    recovered = tmp_path / "neon.db"
    _damaged(recovered)
    with _target(recovered):
        command.upgrade(_config(), "head")

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
                "indexes": {
                    index["name"]: (tuple(index["column_names"]), bool(index["unique"]))
                    for index in inspector.get_indexes(table)
                },
            }
            for table in sorted(inspector.get_table_names())
            if table != "alembic_version"
        }

    recovered_engine = create_engine(f"sqlite:///{recovered}")
    try:
        assert describe(recovered_engine) == describe(declared_engine)
    finally:
        recovered_engine.dispose()
        declared_engine.dispose()


def test_upgrade_is_repeatable_from_the_revision_before_it(tmp_path):
    """`0010` applied twice over the same database is the same as applied once.

    Not a hypothetical: it is what a retried deploy does after a `stamp` that was rolled back, and
    an idempotent migration whose second run fails is only half a fix.
    """
    database = tmp_path / "twice.db"
    with _target(database):
        command.upgrade(_config(), BILLING)
        command.downgrade(_config(), BEFORE)
        command.upgrade(_config(), BILLING)
        command.downgrade(_config(), BEFORE)
        command.upgrade(_config(), "head")

    assert _stamp(database) == "0011_retention_purge"


def test_downgrade_unwinds_a_partial_state_instead_of_dying_in_it(tmp_path):
    """The other half of the guard, and the reason `downgrade` is checked too.

    A database in the incident's state that someone stamps `0010` — the plausible wrong move — must
    still be able to come back down. Before the guard the downgrade died on the index it was asked
    to drop from a table that was never fully built, leaving the database further from clean than
    when it started.
    """
    database = tmp_path / "partial.db"
    _damaged(database)

    with _target(database):
        command.stamp(_config(), BILLING)  # the wrong move, made deliberately
        command.downgrade(_config(), BEFORE)

    assert _stamp(database) == BEFORE
    assert "organization_billing" not in _tables(database)
    assert "billing_invoices" not in _tables(database)


# ==============================================================================================
# the diagnosis is not guesswork
# ==============================================================================================


def _diagnose(database: Path) -> tuple[int, str]:
    """Run `--diagnose` against `database` and return its exit code and everything it logged.

    A handler of its own rather than `caplog`: `alembic/env.py` calls `fileConfig(alembic.ini)`,
    which replaces the root logger's handlers — including the one pytest installed — and sets the
    root level to WARNING. Any test that builds its fixture by running a migration therefore loses
    both the INFO lines and pytest's capture, which is a confusing thing to debug from an empty
    assertion message. Attaching to the `migrate` logger directly is immune to all of it.
    """
    import logging

    import scripts.migrate as migrate

    class _Capture(logging.Handler):
        def __init__(self) -> None:
            super().__init__()
            self.lines: list[str] = []

        def emit(self, record: logging.LogRecord) -> None:
            self.lines.append(record.getMessage())

    handler = _Capture()
    logger = logging.getLogger("migrate")
    previous_level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        with _target(database):
            code = migrate.diagnose()
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)
    return code, "\n".join(handler.lines)


def test_diagnose_names_the_conflict_and_refuses_to_recommend_stamping(tmp_path):
    """The distinction the whole flag exists for.

    `0010`'s tables are present *and* its column is missing. A revision is a unit, so half of it
    present means something other than that revision built those objects — and stamping would
    therefore lose the other half permanently. The output has to say so, because "relation already
    exists" reads exactly like a lost stamp and the two repairs are incompatible.
    """
    database = tmp_path / "neon.db"
    _damaged(database)

    code, output = _diagnose(database)

    assert code == 1
    assert "CONFLICT" in output
    assert "organization_billing" in output
    assert "api_usage_logs.invoices_processed" in output
    assert "Do NOT stamp" in output
    assert "0011_retention_purge: clean" in output, "a revision with no conflict must say so"


def test_diagnose_recommends_stamping_when_the_revision_really_did_apply(tmp_path):
    """The genuine lost stamp, which is the case where `alembic stamp` is the right answer.

    Built by applying `0010` in full and then rewinding only `alembic_version` — which is what a
    `stamp` against the wrong revision, or a crash between the DDL and the version row on a
    database with non-transactional DDL, leaves behind.
    """
    database = tmp_path / "lost-stamp.db"
    with _target(database):
        command.upgrade(_config(), BILLING)

    connection = sqlite3.connect(database)
    connection.execute("UPDATE alembic_version SET version_num = ?", (BEFORE,))
    connection.commit()
    connection.close()

    code, output = _diagnose(database)

    assert code == 1
    assert "already present" in output
    assert f"alembic stamp {BILLING}" in output
    assert "Do NOT stamp" not in output


def test_diagnose_is_quiet_on_a_database_that_is_simply_behind(tmp_path):
    """A normal pending migration is not a conflict, and must not be reported as one.

    Exit 0 specifically: this is usable as a deploy pre-flight, so "there is work to do" and
    "something is wrong" have to be different answers.
    """
    database = tmp_path / "behind.db"
    with _target(database):
        command.upgrade(_config(), BEFORE)

    code, output = _diagnose(database)

    assert code == 0
    assert "CONFLICT" not in output
    assert BILLING in output


def test_diagnose_reports_nothing_pending_at_head(tmp_path):
    database = tmp_path / "current.db"
    with _target(database):
        command.upgrade(_config(), "head")

    code, output = _diagnose(database)

    assert code == 0
    assert "nothing pending" in output
