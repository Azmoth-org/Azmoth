"""Retry the failures that are worth retrying, and only those.

A retry is a bet that the same call will behave differently. That bet is good for a connection the
database dropped during a failover and bad for everything else: a malformed XML document does not
become well formed, a rule violation does not stop being a violation, and a `422` retried three
times is three times the load for the same answer. So the predicate is an allow-list of transient
failure types — never "retry anything that raised".

**Why not tenacity.** It would do this well, and it would be a fifth pinned runtime dependency for
about sixty lines. The deciding factor was testability: the two things that make retry logic hard
to trust are the sleeping and the jitter, and both are injected here (`sleeper`, `jitter`), so the
tests assert the actual backoff sequence rather than waiting seven seconds to observe it.

**Backoff.** Exponential from `base_delay`, doubling, with full jitter — the delay before attempt
*n* is a uniform draw from `[0, base * 2^(n-1)]`, capped at `max_delay`. Full jitter rather than a
fixed sequence because the failure this protects against is a database restart, and a restart
releases every waiting worker at once: identical backoff schedules would send them all back in the
same millisecond and knock it over again.

**What is wrapped.** Database writes (`app.services.proposal_store`) and the Soufflé subprocess
(`app.solvers.souffle_engine`). Not the solve itself — Clingo is deterministic and in-process, so a
timeout retried is a timeout paid twice.
"""

from __future__ import annotations

import asyncio
import functools
import logging
import random
import time
from collections.abc import Awaitable, Callable, Iterable
from typing import Any, TypeVar

log = logging.getLogger(__name__)

T = TypeVar("T")

#: Attempts in total, not retries after the first: 3 means one call and two more if it fails.
DEFAULT_ATTEMPTS = 3
DEFAULT_BASE_DELAY_SECONDS = 1.0
DEFAULT_MAX_DELAY_SECONDS = 8.0


def backoff_delays(
    attempts: int = DEFAULT_ATTEMPTS,
    *,
    base_delay: float = DEFAULT_BASE_DELAY_SECONDS,
    max_delay: float = DEFAULT_MAX_DELAY_SECONDS,
    jitter: Callable[[float, float], float] = random.uniform,
) -> list[float]:
    """The wait before each retry: `attempts - 1` values, exponential with full jitter.

    Exposed separately from the decorators so the schedule can be asserted on directly. With
    `jitter=lambda _lo, hi: hi` it degrades to the plain exponential sequence, which is what the
    tests pin.
    """
    return [
        jitter(0.0, min(base_delay * (2**index), max_delay)) for index in range(max(attempts - 1, 0))
    ]


def _describe(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"


def retry_transient(
    *,
    transient: Iterable[type[BaseException]],
    predicate: Callable[[BaseException], bool] | None = None,
    on_exhausted: Callable[[BaseException, int], BaseException] | None = None,
    attempts: int = DEFAULT_ATTEMPTS,
    base_delay: float = DEFAULT_BASE_DELAY_SECONDS,
    max_delay: float = DEFAULT_MAX_DELAY_SECONDS,
    jitter: Callable[[float, float], float] = random.uniform,
    sleeper: Callable[[float], None] | None = None,
    description: str = "",
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Wrap a **synchronous** call so listed transient failures are retried with backoff.

    `transient` is the allow-list. Anything not in it propagates from the first attempt, unchanged
    and untimed — that is the guarantee that a deterministic `400` or `422` is never retried.

    `predicate` narrows the allow-list where the *type* is not enough to decide. SQLAlchemy is the
    reason it exists: `OperationalError` is raised both for a connection the server dropped and for
    a table that does not exist, and only the first is worth a second attempt. See
    `app.db.retry.is_transient_database_error`.

    `on_exhausted` converts the last failure into what the caller should see once the attempts are
    spent; without it the original exception is re-raised. This is where a driver-level
    `OperationalError` becomes a `TransientDatabaseError` carrying a `Retry-After`, so the HTTP
    layer never has to know what SQLAlchemy calls a dropped socket.
    """
    transient_types = tuple(transient)
    sleep = sleeper or time.sleep

    def decorate(func: Callable[..., T]) -> Callable[..., T]:
        label = description or func.__qualname__

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            delays = backoff_delays(
                attempts, base_delay=base_delay, max_delay=max_delay, jitter=jitter
            )
            last: BaseException | None = None
            for attempt in range(1, attempts + 1):
                try:
                    return func(*args, **kwargs)
                except transient_types as exc:
                    if predicate is not None and not predicate(exc):
                        # The type matched but this instance is not transient — a missing table,
                        # not a dropped socket. Deterministic, so it leaves immediately.
                        raise
                    last = exc
                    if attempt == attempts:
                        break
                    delay = delays[attempt - 1]
                    log.warning(
                        "%s failed (attempt %d/%d), retrying in %.2fs — %s",
                        label,
                        attempt,
                        attempts,
                        delay,
                        _describe(exc),
                    )
                    sleep(delay)
            assert last is not None  # only reachable via the transient branch
            log.error("%s failed after %d attempts — %s", label, attempts, _describe(last))
            raise (on_exhausted(last, attempts) if on_exhausted else last) from last

        return wrapper

    return decorate


def retry_transient_async(
    *,
    transient: Iterable[type[BaseException]],
    predicate: Callable[[BaseException], bool] | None = None,
    on_exhausted: Callable[[BaseException, int], BaseException] | None = None,
    attempts: int = DEFAULT_ATTEMPTS,
    base_delay: float = DEFAULT_BASE_DELAY_SECONDS,
    max_delay: float = DEFAULT_MAX_DELAY_SECONDS,
    jitter: Callable[[float, float], float] = random.uniform,
    sleeper: Callable[[float], Awaitable[None]] | None = None,
    description: str = "",
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """`retry_transient` for coroutines — the database path.

    Separate from the sync version rather than one decorator that sniffs the wrapped function,
    because the sleep has to be `await asyncio.sleep` here: a `time.sleep` inside a coroutine would
    block the event loop for the whole backoff window and stall every other request while waiting
    to retry one of them.
    """
    transient_types = tuple(transient)
    sleep = sleeper or asyncio.sleep

    def decorate(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        label = description or func.__qualname__

        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            delays = backoff_delays(
                attempts, base_delay=base_delay, max_delay=max_delay, jitter=jitter
            )
            last: BaseException | None = None
            for attempt in range(1, attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except transient_types as exc:
                    if predicate is not None and not predicate(exc):
                        raise
                    last = exc
                    if attempt == attempts:
                        break
                    delay = delays[attempt - 1]
                    log.warning(
                        "%s failed (attempt %d/%d), retrying in %.2fs — %s",
                        label,
                        attempt,
                        attempts,
                        delay,
                        _describe(exc),
                    )
                    await sleep(delay)
            assert last is not None
            log.error("%s failed after %d attempts — %s", label, attempts, _describe(last))
            raise (on_exhausted(last, attempts) if on_exhausted else last) from last

        return wrapper

    return decorate


__all__ = [
    "DEFAULT_ATTEMPTS",
    "DEFAULT_BASE_DELAY_SECONDS",
    "DEFAULT_MAX_DELAY_SECONDS",
    "backoff_delays",
    "retry_transient",
    "retry_transient_async",
]
