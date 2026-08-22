"""The engine, the session factory, and the two ways a schema can come to exist.

One `Database` per process. It is built lazily rather than at import time for the same reason the
pipeline is: `import app.main` has to work — for an OpenAPI export, in CI, on a machine with no
Postgres — without opening a connection to anything. Nothing here connects until the first session
is actually used.

**Sessions are short and scoped to one operation.** `Database.session()` is an async context
manager that commits on success and rolls back on any exception. There is no request-scoped session
and no `expire_on_commit=False` convenience: a repository method that returns a detached ORM object
invites a lazy load from a closed session three layers up, which is the classic way an async ORM
starts raising `MissingGreenlet` in production and nowhere else. `proposal_store` therefore converts
every row into a Pydantic model *inside* the session and returns that.

**Two ways to get a schema, and only one of them is allowed in production.** `alembic upgrade head`
is the real path — reviewed, ordered, reversible. `init_models()` (`Base.metadata.create_all`) is
the convenience for the SQLite default and the test suite, and it refuses to run when `APP_ENV` is
`production`: a schema that appeared without a migration cannot be rolled back, and a service that
silently creates its own tables will happily run against a database whose migration history says it
is at a revision it is not.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.config import AppEnv, Settings, get_settings
from app.db.base import Base

log = logging.getLogger(__name__)


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


def _is_memory_sqlite(url: str) -> bool:
    return _is_sqlite(url) and (":memory:" in url or "mode=memory" in url)


def build_engine(settings: Settings) -> AsyncEngine:
    """An `AsyncEngine` configured for whichever dialect `DATABASE_URL` names.

    The two dialects need genuinely different pools, so this is a branch rather than a config dict:

    * **in-memory SQLite** — `StaticPool`, because the database *is* the connection. A pool that
      opens a second connection gets a second, empty database, and a pool that closes the last one
      deletes the schema. `check_same_thread=False` is required because aiosqlite drives the
      connection from its own worker thread.
    * **file SQLite** — no pool sizing worth doing; one writer is a property of the file, not of
      the configuration.
    * **Postgres** — `pool_pre_ping`, so a connection killed by a failover or an idle timeout is
      discovered and replaced instead of surfacing as a 500 on somebody's approval.
    """
    url = settings.database_url

    if _is_memory_sqlite(url):
        return create_async_engine(
            url,
            echo=settings.database_echo,
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )

    if _is_sqlite(url):
        return create_async_engine(url, echo=settings.database_echo)

    return create_async_engine(
        url,
        echo=settings.database_echo,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_pre_ping=True,
    )


class Database:
    """An engine plus its session factory. One per process, disposed with the app."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.engine: AsyncEngine = build_engine(self.settings)
        self.sessionmaker: async_sessionmaker[AsyncSession] = async_sessionmaker(
            self.engine,
            expire_on_commit=False,
            autoflush=False,
        )

    @property
    def url(self) -> str:
        """The URL with any password removed. Safe to log; the raw value is not."""
        return self.engine.url.render_as_string(hide_password=True)

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """One unit of work. Commits on success, rolls back on anything else.

        Rollback-then-re-raise rather than rollback-and-swallow: a failed approval must reach the
        caller as an error, not as a proposal that looks unchanged for no stated reason.
        """
        async with self.sessionmaker() as session:
            try:
                yield session
                await session.commit()
            except BaseException:
                await session.rollback()
                raise

    async def create_all(self) -> None:
        """`CREATE TABLE IF NOT EXISTS` for both tables. See `init_models` for when this is allowed."""
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def drop_all(self) -> None:
        """Tests only. There is no production path that drops the audit log."""
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)

    async def dispose(self) -> None:
        await self.engine.dispose()


class SchemaNotMigrated(RuntimeError):
    """`DATABASE_AUTO_CREATE` was asked for in production, where only Alembic may create a schema."""


class DatabaseNotDurable(RuntimeError):
    """`APP_ENV=production` with a database an approval must not be trusted to live in."""


def assert_production_database(settings: Settings) -> None:
    """In production, refuse to start on anything but Postgres.

    The whole point of this migration is that an approval is durable and auditable. A deployment
    that reached production still on the SQLite default would satisfy every test in the suite and
    none of the reason the work was done: one writer, one file inside a container that is replaced on
    every deploy, no replication, no encryption at rest. A warning would be read once and forgotten;
    a refusal to start cannot be.

    `staging` and `development` are unrestricted on purpose — SQLite is the right choice for a laptop
    and a reasonable one for a throwaway environment. It is `production` that makes a claim.
    """
    if settings.app_env is not AppEnv.PRODUCTION or settings.database_is_durable:
        return
    raise DatabaseNotDurable(
        f"APP_ENV=production with DATABASE_URL pointing at {settings.database_backend!r}. "
        "Approvals in production must be stored in Postgres: set DATABASE_URL to "
        "postgresql+asyncpg://… (infra/docker/docker-compose.yml shows the shape). Refusing to "
        "start rather than accept approvals this deployment cannot be trusted to keep."
    )


async def init_models(database: Database) -> None:
    """Make sure the tables exist, by the route the environment is allowed to use.

    Development and test: create them directly, so `pytest` and `uvicorn app.main:app` need no
    migration step. Production: do nothing, because `alembic upgrade head` ran before this process
    started (the Dockerfile's `CMD` chains them) — and if `DATABASE_AUTO_CREATE` is set anyway,
    fail loudly rather than fabricate a schema Alembic has no record of.
    """
    assert_production_database(database.settings)

    if not database.settings.database_auto_create:
        log.info("database: schema managed by Alembic (auto-create off) at %s", database.url)
        return

    if database.settings.app_env is AppEnv.PRODUCTION:
        raise SchemaNotMigrated(
            "DATABASE_AUTO_CREATE is true with APP_ENV=production. In production the schema must "
            "come from `alembic upgrade head`, so that a rollback exists and the migration history "
            "describes the database. Set DATABASE_AUTO_CREATE=false."
        )

    await database.create_all()
    log.info("database: schema ensured via create_all at %s", database.url)


_database: Database | None = None


def get_database() -> Database:
    """The process-wide `Database`, built on first use."""
    global _database
    if _database is None:
        _database = Database()
    return _database


async def reset_database() -> None:
    """Drop the singleton, disposing its engine first.

    Awaited rather than sync because an undisposed `AsyncEngine` leaks its connections and, on
    SQLite, keeps a file handle open. Tests rebuild the world between cases; without this they
    would accumulate one engine per test.
    """
    global _database
    if _database is not None:
        await _database.dispose()
    _database = None


def set_database(database: Database | None) -> None:
    """Install a `Database` built elsewhere. For tests and for `scripts/`."""
    global _database
    _database = database


__all__ = [
    "Database",
    "DatabaseNotDurable",
    "SchemaNotMigrated",
    "assert_production_database",
    "build_engine",
    "get_database",
    "init_models",
    "reset_database",
    "set_database",
]
