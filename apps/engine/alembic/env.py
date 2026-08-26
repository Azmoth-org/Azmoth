"""Alembic's entry point, wired to the app's own configuration.

Two things are deliberate here.

**The URL comes from `app.config.Settings`, not from `alembic.ini`.** One source of truth for where
the database is: `alembic upgrade head` and `uvicorn app.main:app` read the same `DATABASE_URL`, so
a migration cannot land in one database while the service talks to another. It also means no
connection string — and therefore no password — is ever committed.

**Migrations run through the async engine.** `DATABASE_URL` names an async driver
(`postgresql+asyncpg`, `sqlite+aiosqlite`), and Alembic's machinery is synchronous, so the async
connection is handed to it via `run_sync`. Rewriting the URL to a sync driver instead would mean
requiring `psycopg2` alongside `asyncpg` purely to run migrations, and would let the two paths
disagree about SSL and pooling settings.

`compare_type=True` is on because the alternative is silent: without it, widening a column or
changing `String(64)` to `Text` autogenerates an empty migration and the mismatch is discovered in
production.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection

from app.config import get_settings
from app.db.base import Base

# Imported for its side effect: the mappers have to be registered before `Base.metadata` describes
# anything, or `--autogenerate` cheerfully produces a migration that drops both tables.
from app.db import models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    # `disable_existing_loggers=False` is not cosmetic. fileConfig defaults to True, which silences
    # every logger configured before it — including the one `scripts/migrate.py` uses to report what
    # it did. A deploy log that shows Alembic's chatter but not "migration complete" is worse than
    # no log line at all, because it looks like the script stopped.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata

#: Tables in this database that Alembic does not own.
#:
#: Better Auth keeps its sessions and credentials in the same database as the proposals, and
#: creates them from the Next.js app with its own migrator (`pnpm --filter web auth:migrate`) —
#: see `apps/web/lib/auth.ts`. They are therefore absent from `Base.metadata`, and without this
#: filter the first `alembic revision --autogenerate` run against a real deployment would produce a
#: migration that drops every user account in it.
#:
#: A denylist rather than "only manage what is in the metadata", because the latter is what
#: autogenerate is *for*: a table that disappears from `app/db/models.py` should still produce a
#: drop. This names the four tables that are somebody else's.
BETTER_AUTH_TABLES = frozenset({"user", "session", "account", "verification"})


def _include_object(_object, name, type_, _reflected, _compare_to) -> bool:
    """Keep Better Auth's tables out of autogenerate. No effect on `upgrade`/`downgrade`."""
    return not (type_ == "table" and name in BETTER_AUTH_TABLES)


def _url() -> str:
    return get_settings().database_url


def _configure(**kwargs) -> None:
    context.configure(
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        include_object=_include_object,
        # SQLite cannot ALTER a column in place. Batch mode rewrites the table instead, so a future
        # migration written against Postgres still applies to a local SQLite database.
        render_as_batch=_url().startswith("sqlite"),
        **kwargs,
    )


def run_migrations_offline() -> None:
    """`alembic upgrade head --sql`: emit the DDL without connecting to anything."""
    _configure(url=_url(), literal_binds=True, dialect_opts={"paramstyle": "named"})

    with context.begin_transaction():
        context.run_migrations()


def _run(connection: Connection) -> None:
    _configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Connect with the app's own engine and run the migrations inside it."""
    from app.db.session import build_engine

    engine = build_engine(get_settings())
    try:
        async with engine.connect() as connection:
            await connection.run_sync(_run)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
