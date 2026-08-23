"""Which database failures are worth retrying, and the decorator that does it.

SQLAlchemy does not have a "transient" exception class, and the type alone cannot decide:
`OperationalError` is what asyncpg raises for a connection the server closed during a failover and
also what SQLite raises for a table that does not exist. Retrying the first is the whole point;
retrying the second is three attempts and two sleeps to reach the same wrong answer.

So the test is `connection_invalidated` — the flag SQLAlchemy sets when it has decided the
connection itself is unusable and has evicted it from the pool. That is exactly the condition under
which a second attempt gets a *new* connection and can therefore behave differently.

**Retrying a write is safe here because the status machine makes it safe**, not because the
retries are clever. A retried attempt only happens when the connection was invalidated, which
rolls the transaction back — so nothing was committed and the write is simply redone. In the one
racy case that remains (the socket dies after `COMMIT` reached the server but before the
acknowledgement came back) the second attempt finds the proposal already in its new status and
raises `IllegalTransitionError`, which is a `409` rather than a second approval. Confusing to read
in a log, correct in the database, and much better than the alternative of silently approving twice.
"""

from __future__ import annotations

import functools
from collections.abc import Awaitable, Callable
from typing import TypeVar

from sqlalchemy.exc import DBAPIError, DisconnectionError, InterfaceError
from sqlalchemy.exc import TimeoutError as SQLAlchemyPoolTimeout

from app.config import get_settings
from app.core.retry import retry_transient_async
from app.errors import TransientDatabaseError

T = TypeVar("T")

#: Types that *may* be transient. Narrowed further by `is_transient_database_error`.
TRANSIENT_DATABASE_TYPES: tuple[type[BaseException], ...] = (
    DBAPIError,
    DisconnectionError,
    InterfaceError,
    SQLAlchemyPoolTimeout,
)


def is_transient_database_error(exc: BaseException) -> bool:
    """True when a second attempt would get a fresh connection and could therefore succeed.

    `DisconnectionError` and the pool's own `TimeoutError` are transient by definition — the first
    says the connection died, the second says none was free in time. For everything else the
    verdict is SQLAlchemy's own `connection_invalidated`, which is set precisely when the driver
    error was bad enough to evict the connection from the pool.

    An `IntegrityError` is a `DBAPIError` and is deliberately excluded by this test: a unique
    violation is a fact about the data and will be a fact about the data on the third attempt too.
    """
    if isinstance(exc, (DisconnectionError, SQLAlchemyPoolTimeout)):
        return True
    if isinstance(exc, InterfaceError):
        # "connection is closed" / "cannot operate on a closed database" — the connection is gone,
        # which is the case a retry exists for.
        return True
    if isinstance(exc, DBAPIError):
        return bool(exc.connection_invalidated)
    return False


def _as_transient_failure(exc: BaseException, attempts: int) -> BaseException:
    return TransientDatabaseError(
        "Die Datenbank war nicht erreichbar. Die Anfrage wurde "
        f"{attempts}× versucht und ist jedes Mal an der Verbindung gescheitert. Der Vorgang wurde "
        "nicht gespeichert — bitte in einigen Sekunden erneut senden.",
        details={
            "attempts": attempts,
            "last_error": f"{type(exc).__name__}: {exc}",
            "operation": "database",
        },
    )


def retry_database(
    description: str = "",
    **overrides,
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """Wrap one store method so a dropped connection is retried, then reported honestly.

    The attempt count and the base delay are read from `Settings` **on each call**, not captured
    when the decorator runs. That costs one closure per invocation — nothing beside a database
    round trip — and buys two things worth more than that: `DB_RETRY_ATTEMPTS` actually configures
    a running deployment rather than whatever the environment happened to hold at import time, and
    a test can shorten the backoff by pointing `get_settings` somewhere else instead of waiting out
    a real three-second schedule.

    `overrides` go straight to `retry_transient_async` and win over the settings, which is how the
    tests inject a counting `sleeper` and a deterministic `jitter`.
    """

    def decorate(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            settings = get_settings()
            configured = {
                "attempts": settings.db_retry_attempts,
                "base_delay": settings.db_retry_base_delay_seconds,
                **overrides,
            }
            wrapped = retry_transient_async(
                transient=TRANSIENT_DATABASE_TYPES,
                predicate=is_transient_database_error,
                on_exhausted=_as_transient_failure,
                description=description or func.__qualname__,
                **configured,
            )(func)
            return await wrapped(*args, **kwargs)

        return wrapper

    return decorate


__all__ = [
    "TRANSIENT_DATABASE_TYPES",
    "is_transient_database_error",
    "retry_database",
]
