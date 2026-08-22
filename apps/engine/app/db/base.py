"""The declarative base, and the column types that have to work on two dialects at once.

The engine is developed against SQLite (`sqlite+aiosqlite`, the `DATABASE_URL` default) and
deployed against Postgres (`postgresql+asyncpg`). Every type below therefore has to mean the same
thing in both, and the two that do not translate for free are spelled out here rather than at each
use site:

``JSONVariant``
    ``JSONB`` on Postgres — indexable, deduplicated keys, no reparse per read — and SQLAlchemy's
    portable ``JSON`` (a TEXT column) everywhere else.

``UUIDVariant``
    Postgres' native ``uuid``, and ``CHAR(32)`` elsewhere. SQLAlchemy's ``Uuid`` already does this;
    it is named here so the intent is greppable and so `native_uuid` is set explicitly rather than
    inherited from a default that could change.

The one thing this file will NOT do is paper over a difference that matters. Timezone handling is
the example: ``TIMESTAMP WITH TIME ZONE`` on Postgres round-trips an aware datetime, and SQLite has
no timestamp type at all, so it hands back a naive one. Rather than pretend otherwise, everything
is written in UTC and `app.db.models.as_utc` re-attaches the timezone on the way out.
"""

from __future__ import annotations

from sqlalchemy import JSON, DateTime, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase

#: JSONB where it exists, portable JSON otherwise.
JSONVariant = JSON().with_variant(JSONB(), "postgresql")

#: Native `uuid` on Postgres, CHAR(32) elsewhere.
UUIDVariant = Uuid(native_uuid=True)

#: Aware on Postgres, naive-but-UTC on SQLite. Read through `as_utc`.
TimestampVariant = DateTime(timezone=True)


class Base(DeclarativeBase):
    """Shared metadata for every table.

    Nothing is added to it. A base class with behaviour would put logic below the repository, and
    the point of the seam is that the repository is the only place the two layers meet.
    """
