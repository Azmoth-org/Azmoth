"""Count what each partner consumed, and add it up when they ask.

Two halves, and they answer to different people. `UsageMeter` writes one row per attributable
request, which is what an invoice is eventually built from. `UsageStore.summarise` reads them back
for `GET /api/v1/settings/usage`, which is what a partner looks at to see what they are spending.

## The write path buffers, and here is the exact trade

Rows accumulate in memory and are flushed in batches. What that buys is that the hot path —
`POST /audit/single`, which a PVS vendor may call a hundred times a minute — does not pay a database
round trip per call, and a database hiccup does not add latency to an audit. What it costs is
bounded: a process killed with a partial buffer loses those rows.

Both numbers are small and deliberate. `FLUSH_THRESHOLD` is 25 and `FLUSH_AFTER_SECONDS` is 15, so
at any moment the exposure is at most 25 requests or 15 seconds of traffic, whichever comes first,
and a clean shutdown loses nothing because the lifespan flushes.

**Be honest about what this is.** It is metering good enough to price a pilot and to answer "what
are we using", not a financial ledger. The day an invoice built from it is disputed, the buffer has
to go and the write has to become synchronous and transactional with the request. That is a
deliberate future change, not an oversight, and it is one line: flush on every record.

## Why the flush is not a background task

The obvious design — an `asyncio` task flushing on a timer — was tried in the observability work and
is wrong on this stack. `DATABASE_URL` defaults to SQLite, whose in-memory form shares one
connection through `StaticPool` and whose file form has exactly one writer, so a task transacting
while requests transact interleaves `BEGIN`/`COMMIT`/`ROLLBACK` on that connection — and a rollback
from the flush discards a *request's* write. It cost three test files failing at a distance before
it was found.

So the flush happens **inside a request**, on whichever one finds the buffer full or stale, plus
once from the lifespan on shutdown. No task, no concurrency, no interleaving. One unlucky request
per twenty-five pays for a single batched `INSERT`, which is cheaper than the twenty-five individual
ones it replaces.

## What is never recorded

No request body, no response body, no filename, no Ziffer, no euro amount. A usage row is the
*shape* of a request — who, which endpoint, how many bytes, how long, what status — and nothing
about the invoice inside it. That is what lets this table be read by whoever handles billing rather
than only by somebody cleared for patient data.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import Integer, func, select

from app.db.models import ApiUsageRecord, as_utc, utcnow
from app.db.session import Database, get_database

log = logging.getLogger(__name__)

#: How many rows may wait in memory before the next request flushes them.
FLUSH_THRESHOLD = 25

#: How stale the oldest buffered row may get before the next request flushes, in seconds. Checked on
#: arrival rather than on a timer — see the module docstring on why there is no background task.
FLUSH_AFTER_SECONDS = 15.0

#: A hard ceiling, far above the threshold, at which rows are dropped rather than buffered.
#:
#: Reachable only if the database has been refusing writes for a long time. Dropping is the right
#: answer then: the alternative is a buffer that grows until the process dies, which loses the rows
#: anyway and takes the audit service with it. The drop is logged at `error` so it is not silent.
MAX_BUFFERED_ROWS = 5_000


@dataclass(frozen=True)
class PendingUsage:
    """One request, waiting to be written. Immutable so a flush cannot race a mutation."""

    organization_id: str
    api_key_id: str | None
    endpoint: str
    status_code: int
    duration_ms: int
    bytes_processed: int
    at: datetime


class UsageMeter:
    """The buffer, and the decision about when to empty it.

    One per process, held by `app.api.deps`. It must be a singleton for the obvious reason — two
    buffers would each flush half the traffic and neither would ever be full — and its lock is
    created in `__init__` for the same reason `BatchAuditService`'s is: an `asyncio.Lock` built at
    module import binds to whatever loop happens to exist then.
    """

    def __init__(self, database: Database | None = None) -> None:
        self._database = database
        self._buffer: list[PendingUsage] = []
        self._oldest_at: float | None = None
        self._lock = asyncio.Lock()

    @property
    def database(self) -> Database:
        return self._database if self._database is not None else get_database()

    @property
    def pending(self) -> int:
        """How many rows are waiting. For the tests, and for a shutdown log line."""
        return len(self._buffer)

    async def record(
        self,
        *,
        organization_id: str,
        api_key_id: str | None,
        endpoint: str,
        status_code: int,
        duration_ms: float,
        bytes_processed: int,
    ) -> None:
        """Buffer one request, and flush if that made the buffer full or if it had gone stale.

        **Never raises.** It is called from the request middleware's `finally`, after the handler
        has already produced an answer, so an exception here would turn a successful audit into a
        `500` over a bookkeeping row. A metering failure is logged and swallowed; a caller must
        never be punished for our accounting.
        """
        try:
            now = time.monotonic()
            entry = PendingUsage(
                organization_id=organization_id,
                api_key_id=api_key_id,
                endpoint=endpoint,
                status_code=status_code,
                duration_ms=int(duration_ms),
                bytes_processed=max(0, bytes_processed),
                at=utcnow(),
            )

            async with self._lock:
                if len(self._buffer) >= MAX_BUFFERED_ROWS:
                    log.error(
                        "usage buffer is full at %d rows and the database is not accepting "
                        "writes; dropping this row rather than growing without bound",
                        len(self._buffer),
                    )
                    return
                self._buffer.append(entry)
                if self._oldest_at is None:
                    self._oldest_at = now
                due = (
                    len(self._buffer) >= FLUSH_THRESHOLD
                    or now - self._oldest_at >= FLUSH_AFTER_SECONDS
                )

            if due:
                await self.flush()
        except Exception:  # noqa: BLE001 - see docstring
            log.exception("could not meter a request; the request itself was unaffected")

    async def flush(self) -> int:
        """Write everything buffered, in one transaction. Returns how many rows landed.

        The buffer is swapped out under the lock and the write happens outside it, so a slow
        database does not block the requests arriving behind it. On failure the rows go back — at
        the *front*, so ordering survives a retry — because losing them silently is the one outcome
        metering must not have.

        Never raises, for the same reason `record` does not: its callers are a request that has
        already answered and a lifespan that is shutting down, and neither can act on the failure.
        """
        async with self._lock:
            if not self._buffer:
                return 0
            batch, self._buffer = self._buffer, []
            self._oldest_at = None

        try:
            async with self.database.session() as session:
                session.add_all(
                    ApiUsageRecord(
                        api_key_id=entry.api_key_id,
                        organization_id=entry.organization_id,
                        endpoint=entry.endpoint,
                        request_count=1,
                        bytes_processed=entry.bytes_processed,
                        duration_ms=entry.duration_ms,
                        status_code=entry.status_code,
                        timestamp=entry.at,
                    )
                    for entry in batch
                )
        except Exception:  # noqa: BLE001 - see docstring
            async with self._lock:
                self._buffer[:0] = batch
                self._oldest_at = self._oldest_at or time.monotonic()
            log.exception("could not flush %d usage row(s); they stay buffered", len(batch))
            return 0

        log.debug("flushed %d usage row(s)", len(batch))
        return len(batch)


# ==============================================================================================
# reading it back
# ==============================================================================================


def month_to_date(now: datetime | None = None) -> tuple[datetime, datetime]:
    """The current calendar month in UTC, `[start, now]`.

    UTC and not the practice's local time, deliberately. A usage figure that shifted by an hour
    twice a year — and whose month boundary therefore moved — would be a number two people could
    compute differently from the same rows. The endpoint states the window it used, so a caller who
    needs a local month can ask for explicit bounds instead.
    """
    moment = now or datetime.now(timezone.utc)
    return moment.replace(day=1, hour=0, minute=0, second=0, microsecond=0), moment


class UsageStore:
    """Reads `api_usage_logs`. Never writes — that is `UsageMeter`'s job and only its job."""

    def __init__(self, database: Database | None = None) -> None:
        self._database = database

    @property
    def database(self) -> Database:
        return self._database if self._database is not None else get_database()

    async def summarise(
        self,
        *,
        organization_id: str,
        since: datetime,
        until: datetime,
    ) -> dict:
        """Totals for one practice over one window, broken down by endpoint and by key.

        Three aggregate queries rather than one fetch and a Python loop. The difference matters at
        the only scale that matters: a busy month is tens of thousands of rows, and pulling them
        into the process to add up would make the endpoint slower the more a customer uses us —
        exactly backwards.

        Every figure is computed under the same `organization_id` filter. There is no code path here
        that can read across practices: the tenant is a required argument, not an option.
        """
        window = (
            ApiUsageRecord.organization_id == organization_id,
            ApiUsageRecord.timestamp >= since,
            ApiUsageRecord.timestamp <= until,
        )
        # `status_code >= 400` as an integer, summed — one expression that works on both dialects,
        # where a `FILTER (WHERE …)` clause would be Postgres-only and a second query would be a
        # second round trip.
        failed = func.sum(func.cast(ApiUsageRecord.status_code >= 400, Integer))

        async with self.database.session() as session:
            totals = (
                await session.execute(
                    select(
                        func.coalesce(func.sum(ApiUsageRecord.request_count), 0),
                        func.coalesce(func.sum(ApiUsageRecord.bytes_processed), 0),
                        func.coalesce(func.sum(ApiUsageRecord.duration_ms), 0),
                        func.coalesce(failed, 0),
                    ).where(*window)
                )
            ).one()

            by_endpoint = (
                (
                    await session.execute(
                        select(
                            ApiUsageRecord.endpoint,
                            func.coalesce(func.sum(ApiUsageRecord.request_count), 0),
                            func.coalesce(func.sum(ApiUsageRecord.bytes_processed), 0),
                            func.coalesce(failed, 0),
                            func.coalesce(func.avg(ApiUsageRecord.duration_ms), 0),
                        )
                        .where(*window)
                        .group_by(ApiUsageRecord.endpoint)
                        .order_by(func.sum(ApiUsageRecord.request_count).desc())
                    )
                )
                .all()
            )

            by_key = (
                (
                    await session.execute(
                        select(
                            ApiUsageRecord.api_key_id,
                            func.coalesce(func.sum(ApiUsageRecord.request_count), 0),
                            func.coalesce(func.sum(ApiUsageRecord.bytes_processed), 0),
                            func.coalesce(failed, 0),
                            func.max(ApiUsageRecord.timestamp),
                        )
                        .where(*window)
                        .group_by(ApiUsageRecord.api_key_id)
                        .order_by(func.sum(ApiUsageRecord.request_count).desc())
                    )
                )
                .all()
            )

        return {
            "organization_id": organization_id,
            "period_start": since,
            "period_end": until,
            "total_requests": int(totals[0] or 0),
            "total_bytes_processed": int(totals[1] or 0),
            "total_duration_ms": int(totals[2] or 0),
            "failed_requests": int(totals[3] or 0),
            "by_endpoint": [
                {
                    "endpoint": row[0],
                    "requests": int(row[1] or 0),
                    "bytes_processed": int(row[2] or 0),
                    "failed_requests": int(row[3] or 0),
                    "average_duration_ms": round(float(row[4] or 0.0), 1),
                }
                for row in by_endpoint
            ],
            "by_key": [
                {
                    # `None` is the web application itself. Named rather than left null, because a
                    # reader looking at their own usage report should not have to guess what an
                    # empty row means — and "the calls we made from the browser" is the honest
                    # answer.
                    "key_id": row[0],
                    "requests": int(row[1] or 0),
                    "bytes_processed": int(row[2] or 0),
                    "failed_requests": int(row[3] or 0),
                    "last_used_at": as_utc(row[4]),
                }
                for row in by_key
            ],
        }


__all__ = [
    "FLUSH_AFTER_SECONDS",
    "FLUSH_THRESHOLD",
    "MAX_BUFFERED_ROWS",
    "PendingUsage",
    "UsageMeter",
    "UsageStore",
    "month_to_date",
]
