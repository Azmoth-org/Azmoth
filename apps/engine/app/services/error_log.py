"""Persist an unhandled failure, so it can be asked about after the fact.

One method. It exists as a store rather than as a function inside the exception handler for the
same reason `ProposalStore` does: the database is injectable, so a test can drive it without the
process-wide singleton, and nothing about writing a row leaks into the handler that catches the
exception.

**Everything here is defensive to a degree that would be wrong anywhere else.** This runs while the
service is already failing. A `500` that also failed to *record* itself is a worse outcome than a
`500` that was recorded, so every value written is truncated to its column, every field is
optional, and the caller (`app.core.observability.record_exception`) catches whatever escapes.
"""

from __future__ import annotations

import logging
from typing import Any

from app.db.models import ErrorLogRecord, utcnow
from app.db.session import Database, get_database

log = logging.getLogger(__name__)

#: How much of an exception's message is kept.
#:
#: A `PadnextSchemaError` can carry every violation in a delivery and run to tens of kilobytes; the
#: first two thousand characters name the failure, and the rest is in the log line this row points
#: at. Truncating here rather than at the column because `Text` has no width to truncate to on
#: Postgres — the row would simply grow without bound.
MAX_MESSAGE_LENGTH = 2000


class ErrorLogStore:
    """Writes to `error_log`, and never to anything else."""

    def __init__(self, database: Database | None = None) -> None:
        self._database = database

    @property
    def database(self) -> Database:
        return self._database if self._database is not None else get_database()

    async def record(self, exc: BaseException, *, context: dict[str, Any]) -> None:
        """One row for one failure. Raises only if the database is unreachable.

        `context` is whatever the request had bound by the time it failed — the request id always,
        and the route, tenant and API key where the request had got far enough for those to be
        known. A failure inside the middleware has none of them, and a row with nulls is still a
        much better record than no row: it says *when*, and it says *what*.
        """
        message = str(exc).strip()
        record = ErrorLogRecord(
            request_id=str(context.get("request_id") or "")[:64],
            occurred_at=utcnow(),
            exception_type=type(exc).__name__[:128],
            message=message[:MAX_MESSAGE_LENGTH],
            http_route=_short(context.get("http_route"), 256),
            http_method=_short(context.get("http_method"), 8),
            organization_id=_short(context.get("organization_id"), 256),
            api_key_id=_short(context.get("key_id"), 64),
        )
        async with self.database.session() as session:
            session.add(record)

        log.info(
            "recorded unhandled %s for request %s",
            record.exception_type,
            record.request_id or "(none)",
        )


def _short(value: Any, limit: int) -> str | None:
    """A column-safe string, or `None`. SQLite would store an over-long value whole and Postgres
    would raise on a write that is otherwise fine — so the truncation happens here, once."""
    if value is None:
        return None
    text = str(value).strip()
    return text[:limit] or None


__all__ = ["MAX_MESSAGE_LENGTH", "ErrorLogStore"]
