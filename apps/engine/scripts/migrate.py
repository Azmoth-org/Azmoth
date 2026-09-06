#!/usr/bin/env python3
"""Bring the database schema up to date. What the container runs before uvicorn.

    python scripts/migrate.py              # alembic upgrade head
    python scripts/migrate.py --check      # report the revision, change nothing (exit 1 if behind)
    python scripts/migrate.py --revision X # upgrade (or downgrade) to a specific revision
    python scripts/migrate.py --diagnose   # why `upgrade head` fails on a table that exists

Why a script and not just `alembic upgrade head` in the Dockerfile's CMD:

* **It waits for the database.** In `docker compose up`, the engine and Postgres start together, and
  Postgres accepts TCP connections a little before it will accept a login. A bare `alembic upgrade
  head` loses that race and the container dies; a compose `depends_on: service_healthy` fixes it
  only when the healthcheck is right, and does nothing at all for a deploy where the database is
  behind a proxy that is up before the database is. `--wait` seconds of retry with a clear log line
  is cheaper than debugging a crash loop.
* **It reports what it did.** "already at head" and "applied 0001_proposals_audit" are different
  events, and on a deploy you want to know which one happened.
* **It resolves the URL exactly as the service does** — `DATABASE_URL` through
  `app.config.Settings`, so it cannot migrate a database the engine will not then use.

Exit codes: 0 success, 1 failure (or, with `--check`, a schema that is behind; with `--diagnose`, a
database whose schema and `alembic_version` disagree).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import re
import sys
import time
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE_ROOT))

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from alembic.runtime.migration import MigrationContext  # noqa: E402
from alembic.script import Script, ScriptDirectory  # noqa: E402
from sqlalchemy import inspect, text  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db.session import build_engine  # noqa: E402

log = logging.getLogger("migrate")


def alembic_config() -> Config:
    config = Config(str(ENGINE_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ENGINE_ROOT / "alembic"))
    return config


async def wait_for_database(seconds: float, interval: float = 1.0) -> None:
    """Poll `SELECT 1` until it answers or the budget runs out.

    Waiting is only ever the right answer for a *server* that has not finished starting. So:

    * **SQLite is never retried.** A local file either opens or it does not, and no amount of waiting
      changes that. Retrying turned "unable to open database file" — a path or permission mistake —
      into sixty seconds of identical warnings with the real message at the top, scrolled away.
    * **A server is retried**, because `docker compose up` starts the engine and Postgres together
      and Postgres accepts TCP a moment before it will accept a login.

    A bad password or a missing database on a *reachable* server is still retried, because the driver
    reports it the same way as a server that is still initialising — and under compose that is
    exactly what it usually is. The budget bounds it, and the final error carries the real message.
    """
    settings = get_settings()
    if settings.database_backend == "sqlite":
        log.info("sqlite: nothing to wait for, a file either opens or it does not")
        return

    deadline = time.monotonic() + seconds
    attempt = 0

    while True:
        attempt += 1
        engine = build_engine(settings)
        try:
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
            if attempt > 1:
                log.info("database reachable after %d attempts", attempt)
            return
        except Exception as exc:  # noqa: BLE001 - the driver's exception hierarchy varies
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError(
                    f"database not reachable after {seconds:.0f}s: {exc}"
                ) from exc
            log.warning(
                "database not ready (attempt %d, %.0fs left): %s", attempt, remaining, exc
            )
            await asyncio.sleep(min(interval, max(remaining, 0)))
        finally:
            await engine.dispose()


async def current_revision() -> str | None:
    """The revision this database is stamped with, or None if it has never been migrated."""
    engine = build_engine(get_settings())
    try:
        async with engine.connect() as connection:
            return await connection.run_sync(
                lambda sync_connection: MigrationContext.configure(
                    sync_connection
                ).get_current_revision()
            )
    finally:
        await engine.dispose()


def head_revision() -> str | None:
    return ScriptDirectory.from_config(alembic_config()).get_current_head()


# ==============================================================================================
# --diagnose
# ==============================================================================================
#
# `alembic upgrade head` failing with "relation X already exists" says what broke and nothing about
# why, and the four things it can mean want four different responses:
#
#   the schema is ahead of `alembic_version`   — something created tables outside Alembic
#   a migration applied but was not stamped    — safe to `stamp`, nothing left to apply
#   the wrong database                         — the tables belong to another deployment
#   a downgrade stopped halfway                — objects from one revision partly present
#
# Guessing between them over a production database is how a `stamp head` gets typed at a database
# that is genuinely missing a column, and the schema then silently disagrees with the models until
# something reads it. So this reflects what is actually there and reports it, per pending revision.

#: `op.create_table("name", …)`. The migrations in this history are hand-written and all use this
#: literal form; a revision that built a table some other way simply would not be scanned, which is
#: why the verdicts below are worded as evidence rather than as instructions.
_CREATE_TABLE = re.compile(r"""op\.create_table\(\s*["']([^"']+)["']""")

#: `op.add_column("table", sa.Column("name", …))`, across the line break Black puts in it.
_ADD_COLUMN = re.compile(
    r"""op\.add_column\(\s*["']([^"']+)["'],\s*sa\.Column\(\s*["']([^"']+)["']""", re.S
)


def _objects_created_by(script: Script) -> tuple[set[str], set[tuple[str, str]]]:
    """The tables and (table, column) pairs a revision's source says it creates."""
    source = Path(script.path).read_text(encoding="utf-8")
    # Only the upgrade half: `downgrade` names the same objects in `drop_` calls, and a regex that
    # read the whole file would be fine here but would misread any migration that re-creates a
    # table on the way down.
    upgrade = source.split("def downgrade(", 1)[0]
    return set(_CREATE_TABLE.findall(upgrade)), set(_ADD_COLUMN.findall(upgrade))


async def _reflect() -> tuple[set[str], dict[str, set[str]]]:
    """Every table in the database, and the column names of each."""
    engine = build_engine(get_settings())
    try:
        async with engine.connect() as connection:
            return await connection.run_sync(_reflect_sync)
    finally:
        await engine.dispose()


def _reflect_sync(connection) -> tuple[set[str], dict[str, set[str]]]:
    inspector = inspect(connection)
    tables = set(inspector.get_table_names())
    return tables, {
        table: {column["name"] for column in inspector.get_columns(table)} for table in tables
    }


def _pending(current: str | None, head: str | None) -> list[Script]:
    """The revisions between `current` and `head`, in the order `upgrade` would apply them."""
    directory = ScriptDirectory.from_config(alembic_config())
    return list(reversed(list(directory.iterate_revisions(head, current))))


def diagnose() -> int:
    """Report why the schema and `alembic_version` disagree. Changes nothing.

    Returns 0 when they agree, 1 when they do not — so this is usable as a deploy pre-flight.
    """
    head = head_revision()
    current = asyncio.run(current_revision())
    tables, columns = asyncio.run(_reflect())

    log.info("current revision: %s", current or "<none — no alembic_version row>")
    log.info("head revision   : %s", head)
    log.info("tables present  : %d", len(tables))

    if "alembic_version" not in tables and tables:
        log.warning(
            "there is NO alembic_version table, but %d tables exist. This database was built by "
            "something other than Alembic — `Base.metadata.create_all` (DATABASE_AUTO_CREATE) is "
            "the usual one. See the verdicts below for which revision it corresponds to.",
            len(tables),
        )

    pending = _pending(current, head)
    if not pending:
        log.info("nothing pending — schema and alembic_version agree")
        return 0

    log.info("pending: %s", ", ".join(script.revision for script in pending))

    conflicted = False
    for script in pending:
        created, added = _objects_created_by(script)
        present_tables = sorted(name for name in created if name in tables)
        absent_tables = sorted(name for name in created if name not in tables)
        present_columns = sorted(
            f"{table}.{column}" for table, column in added if column in columns.get(table, ())
        )
        absent_columns = sorted(
            f"{table}.{column}" for table, column in added if column not in columns.get(table, ())
        )

        if not present_tables and not present_columns:
            log.info("%s: clean — nothing it creates exists yet", script.revision)
            continue

        conflicted = True
        log.error(
            "%s: CONFLICT — already present: %s",
            script.revision,
            ", ".join(present_tables + present_columns),
        )
        if absent_tables or absent_columns:
            # A revision is a unit. Half of it present means whatever created those objects was
            # not this revision — it did not know the revision existed, so it created what the
            # *models* declare and skipped what was already there. That is create_all's signature.
            log.error(
                "%s: but still missing: %s — so this revision did NOT half-apply. Something "
                "created those objects outside Alembic (create_all, or a hand-written CREATE). "
                "Do NOT stamp: the missing objects would never be created. Run this script "
                "normally — %s is idempotent and will fill in only what is absent.",
                script.revision,
                ", ".join(absent_tables + absent_columns),
                script.revision,
            )
        else:
            # Everything this revision builds is already there, so applying it would be a no-op.
            # That is either a lost stamp or a database that was migrated by a different Alembic
            # root; both are repaired by recording it.
            log.error(
                "%s: everything it creates is already present, so it has nothing left to do. "
                "Either it applied and the stamp was lost, or this schema came from elsewhere. "
                "Confirm the second by checking that the rows in those tables are the ones you "
                "expect, then: alembic stamp %s",
                script.revision,
                script.revision,
            )

    if not conflicted:
        log.info(
            "no conflicts — `python scripts/migrate.py` will apply %d revision(s)", len(pending)
        )
        return 0
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--revision",
        default="head",
        help="target revision (default: head). Also accepts a downgrade target.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="report the current and head revisions without changing anything; "
        "exit 1 if the database is behind",
    )
    parser.add_argument(
        "--diagnose",
        action="store_true",
        help="report why `upgrade head` conflicts with the existing schema, per pending revision; "
        "changes nothing; exit 1 if the schema and alembic_version disagree",
    )
    parser.add_argument(
        "--wait",
        type=float,
        default=30.0,
        help="seconds to wait for the database to accept connections (default: 30, 0 to fail fast)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    # Explicit, not inherited. Alembic's `env.py` runs `fileConfig(alembic.ini)`, which sets the
    # root logger to WARNING — so a logger relying on root's level goes quiet halfway through this
    # script, exactly when it has something to report.
    log.setLevel(logging.INFO)

    settings = get_settings()
    # Rendered without the password: this line goes to a deploy log.
    engine = build_engine(settings)
    url = engine.url.render_as_string(hide_password=True)
    asyncio.run(engine.dispose())
    log.info("database: %s", url)

    try:
        if args.wait > 0:
            asyncio.run(wait_for_database(args.wait))

        if args.diagnose:
            return diagnose()

        head = head_revision()
        current = asyncio.run(current_revision())

        if args.check:
            log.info("current revision: %s", current or "<none — never migrated>")
            log.info("head revision   : %s", head)
            if current == head:
                log.info("schema is up to date")
                return 0
            log.error("schema is BEHIND: run `alembic upgrade head` (or this script without --check)")
            return 1

        if current == head and args.revision == "head":
            log.info("already at head (%s) — nothing to apply", head)
            return 0

        log.info("upgrading %s -> %s", current or "<none>", args.revision)
        command.upgrade(alembic_config(), args.revision)
        log.info("migration complete: now at %s", asyncio.run(current_revision()))
        return 0
    except Exception as exc:  # noqa: BLE001 - this is a CLI boundary
        log.error("migration failed: %s", exc)
        if "already exists" in str(exc):
            # The specific failure `--diagnose` was written for. Pointing at it from the message is
            # the difference between a ten-minute fix and an afternoon of reading Alembic internals
            # in a deploy log.
            log.error(
                "this looks like a schema that exists without a matching alembic_version row. "
                "Run `python scripts/migrate.py --diagnose` — it reports, per pending revision, "
                "which objects are already there and whether stamping is safe."
            )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
