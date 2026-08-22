#!/usr/bin/env python3
"""Bring the database schema up to date. What the container runs before uvicorn.

    python scripts/migrate.py              # alembic upgrade head
    python scripts/migrate.py --check      # report the revision, change nothing (exit 1 if behind)
    python scripts/migrate.py --revision X # upgrade (or downgrade) to a specific revision

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

Exit codes: 0 success, 1 failure (or, with `--check`, a schema that is behind).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE_ROOT))

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from alembic.runtime.migration import MigrationContext  # noqa: E402
from alembic.script import ScriptDirectory  # noqa: E402
from sqlalchemy import text  # noqa: E402

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
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
