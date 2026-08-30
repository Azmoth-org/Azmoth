"""A per-key request budget, kept in this process's memory.

Two limits, both per API key rather than per organisation:

    POST /api/v1/audit/single    RATE_LIMIT_SINGLE_PER_MINUTE   (100/min)
    POST /api/v1/audit/bulk      RATE_LIMIT_BULK_PER_HOUR       (10/hour)

Per key and not per practice on purpose. A billing centre that runs two integrations takes two
keys, and a runaway loop in one of them then cannot spend the other's budget — the blast radius of
a client bug is the integration that has it. It also makes the limit legible in a support
conversation: the answer to "why are we being throttled" is a key id, which is a thing both sides
can look at.

**The window is fixed, not sliding.** A counter per `(key, endpoint, window index)`, where the
index is `floor(now / window)`. That admits the classic burst — 100 requests in the last second of
one minute and 100 in the first second of the next — and the alternative costs a timestamp per
request per key to close a hole that does not matter here. What this limit protects is a Soufflé
subprocess pool from a client in a `while True`, and a 2× burst across a boundary does not
threaten it. A sliding window is the right change the day the limit becomes a billing tier rather
than a safety valve.

**The honest caveat: this counts one process's share.** The state is a dict in memory. Under
`--workers 4` each worker counts its own requests, so the effective limit is four times the
configured one; behind two containers, eight. That is the same single-process assumption the batch
recovery already documents, reached from the other direction, and it is why `RATE_LIMIT_ENABLED`
exists — a deployment with a real gateway in front turns this off rather than having two limiters
disagree. What it is not is a reason to skip it: a single-container MVP is exactly the shape this
protects, and an in-process counter is the whole of what can be built without the Redis this stack
deliberately does not have.

Memory is bounded by eviction rather than by a cap: entries older than one full window are dropped
whenever the map is touched, so the map holds at most the keys that have been active in the last
two windows. A partner with 50 keys costs 50 integers.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends

from app.api.apikeys import RequestApiKey
from app.config import get_settings
from app.errors import RateLimitExceeded
from app.services.api_keys import AuthenticatedKey

log = logging.getLogger(__name__)

MINUTE_SECONDS = 60
HOUR_SECONDS = 3600


@dataclass(frozen=True)
class Decision:
    """What the limiter concluded, whether or not it refused.

    Carried out of `check` rather than raised from it, because the headers (`X-RateLimit-*`) go on
    a **successful** response too — a client that can see it has 4 of 100 requests left can slow
    down before it is refused, which is the entire point of publishing them.
    """

    allowed: bool
    limit: int
    remaining: int
    window_seconds: int
    #: Seconds until the current window rolls over. Always at least 1: a `Retry-After: 0` invites
    #: an immediate retry that would be refused again.
    reset_after: int

    def headers(self) -> dict[str, str]:
        """The conventional trio, as every gateway spells them."""
        return {
            "X-RateLimit-Limit": str(self.limit),
            "X-RateLimit-Remaining": str(max(0, self.remaining)),
            "X-RateLimit-Reset": str(self.reset_after),
        }


class FixedWindowLimiter:
    """`{(key, bucket, window): count}`, behind a lock.

    A `threading.Lock` and not an `asyncio.Lock`, because FastAPI dispatches a sync path function
    to its threadpool and an async one to the loop, and both kinds of endpoint are limited here.
    The critical section is a dict lookup and an integer increment — microseconds — so a mutex
    shared by every request is not a bottleneck at any rate this limit permits.
    """

    def __init__(self) -> None:
        self._counts: dict[tuple[str, str, int], int] = {}
        self._lock = threading.Lock()

    def check(
        self, identity: str, *, bucket: str, limit: int, window_seconds: int, now: float | None = None
    ) -> Decision:
        """Count this request and say whether it is allowed.

        Counts on the refused path as well, and deliberately: a client hammering a limit it has
        already exceeded stays over it until the window rolls, rather than being let back in the
        moment it slows to exactly the ceiling. The counter is what the `X-RateLimit-Remaining`
        header reports, which is why it is clamped at zero rather than allowed to go negative.
        """
        moment = time.monotonic() if now is None else now
        window = int(moment // window_seconds)
        reset_after = max(1, int((window + 1) * window_seconds - moment))
        slot = (identity, bucket, window)

        with self._lock:
            self._evict_stale(bucket, window)
            count = self._counts.get(slot, 0) + 1
            self._counts[slot] = count

        return Decision(
            allowed=count <= limit,
            limit=limit,
            remaining=limit - count,
            window_seconds=window_seconds,
            reset_after=reset_after,
        )

    def _evict_stale(self, bucket: str, current_window: int) -> None:
        """Drop closed windows **of this bucket**. Called under the lock.

        The bucket has to be part of the comparison, and getting that wrong is the one way this
        map can lose data it still needs. A window index is `now / window_seconds`, so a shorter
        window produces a *larger* index: at the same instant the minute bucket is on index
        ~29,000,000 and the hour bucket on index ~480,000. An eviction that compared every entry
        against the minute bucket's current index would therefore delete every hour counter in the
        map — silently resetting the bulk-upload budget on the next single-file request, which is
        an accounting hole rather than a tidy-up.

        So each bucket only ever prunes its own, and the two never interpret each other's indices.
        """
        if len(self._counts) < 1024:
            # The common case: a handful of keys. Walking the map on every request to save a few
            # hundred bytes would cost more than it saves.
            return
        stale = [
            slot for slot in self._counts if slot[1] == bucket and slot[2] < current_window
        ]
        for slot in stale:
            del self._counts[slot]

    def reset(self) -> None:
        """Forget everything. For the tests, and for `app.api.deps.reset`."""
        with self._lock:
            self._counts.clear()


#: One limiter for the process, because the budget is per process — see the module docstring. Reset
#: between tests through `app.api.deps.reset()`.
_limiter = FixedWindowLimiter()


def limiter() -> FixedWindowLimiter:
    return _limiter


def _enforce(key: AuthenticatedKey, *, bucket: str, limit: int, window_seconds: int) -> Decision:
    """Apply one budget, raising `RateLimitExceeded` when it is spent.

    The identity counted is the `key_id`, never the token: the limiter's map would otherwise hold a
    live credential in memory for the length of a window, and its keys reach a log line the moment
    anyone debugs it.
    """
    settings = get_settings()
    if not settings.rate_limit_enabled:
        # Not "allow and report": a disabled limiter must not emit `X-RateLimit-*` headers that
        # describe a budget nothing is counting. `Decision.allowed` is checked by the caller and
        # the headers are only attached when the limiter is on.
        return Decision(
            allowed=True, limit=limit, remaining=limit, window_seconds=window_seconds, reset_after=1
        )

    decision = limiter().check(
        key.key_id, bucket=bucket, limit=limit, window_seconds=window_seconds
    )
    if not decision.allowed:
        log.info(
            "api key %s exceeded the %s limit (%d per %ds)",
            key.key_id,
            bucket,
            limit,
            window_seconds,
        )
        window_label = "Minute" if window_seconds == MINUTE_SECONDS else "Stunde"
        raise RateLimitExceeded(
            f"Ratenlimit erreicht: {limit} Anfragen pro {window_label} für diesen API-Schlüssel. "
            f"Wiederholen Sie die Anfrage in {decision.reset_after} Sekunden. — Rate limit "
            f"exceeded: {limit} requests per {window_seconds}s for this API key.",
            limit=limit,
            window_seconds=window_seconds,
            retry_after=decision.reset_after,
            details={"bucket": bucket, "key_id": key.key_id},
        )
    return decision


def limit_single(key: RequestApiKey) -> Decision:
    """The per-minute budget on `POST /api/v1/audit/single`."""
    return _enforce(
        key,
        bucket="single",
        limit=get_settings().rate_limit_single_per_minute,
        window_seconds=MINUTE_SECONDS,
    )


def limit_bulk(key: RequestApiKey) -> Decision:
    """The per-hour budget on `POST /api/v1/audit/bulk`.

    Two orders of magnitude tighter than the single limit, because a bulk upload is two orders of
    magnitude more expensive: one call can be 500 deliveries and 500 Soufflé runs. The budget is
    about the work accepted, not about the requests made.
    """
    return _enforce(
        key,
        bucket="bulk",
        limit=get_settings().rate_limit_bulk_per_hour,
        window_seconds=HOUR_SECONDS,
    )


#: What a path function annotates with. It returns a `Decision` rather than `None` so the route can
#: put the headers on its own response — see `app.api.audit`.
SingleRateLimit = Annotated[Decision, Depends(limit_single)]
BulkRateLimit = Annotated[Decision, Depends(limit_bulk)]


__all__ = [
    "HOUR_SECONDS",
    "MINUTE_SECONDS",
    "BulkRateLimit",
    "Decision",
    "FixedWindowLimiter",
    "SingleRateLimit",
    "limit_bulk",
    "limit_single",
    "limiter",
]
