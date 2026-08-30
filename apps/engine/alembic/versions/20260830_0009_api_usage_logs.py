"""api_usage_logs — what a partner consumed, so it can be counted and invoiced.

Revision ID: 0009_api_usage_logs
Revises: 0008_error_log
Create Date: 2026-08-30

The gap this closes is commercial rather than technical: **you cannot sell an API you cannot
meter.** Before it, the only record of a key being used was `api_keys.last_used_at`, one overwritten
timestamp — enough to know a key is alive, useless for "how many audits did this billing centre run
in August", which is the sentence an invoice is made of.

    api_usage_logs   api_key_id, organization_id, endpoint, request_count, bytes_processed,
                     duration_ms, status_code, timestamp

**One row per attributable request**, written for calls from both doors: `api_key_id` is set for a
partner and `NULL` for one the web tier proxied under a session. Keeping both means "what is this
practice's total load" and "what is this integration costing us" are the same table with a different
`WHERE`. A request that never resolved a tenant writes nothing — there is nobody to bill.

**No foreign key to `api_keys`.** Usage by a key that is later deleted is still usage that happened,
and a constraint here would make tidying that table silently destroy billing history. The same
reasoning as every other id in this schema that points at a row somebody else owns.

**Two composite indexes, both tenant- or key-leading**, because every read is `WHERE
organization_id = ? AND timestamp >= ?` — the usage report — or the same with `api_key_id`, which is
the per-key breakdown inside it. The single-column indexes on `status_code` and `timestamp` serve
the operational question instead: how many calls failed, and when.

**Retention is expected and nothing here prevents it.** This is operational counting, not a record
anybody's liability attaches to; rolling a month up into one row per key per endpoint is the obvious
first optimisation, which is why `request_count` is a column rather than an implied 1.

Written by hand for the same reason as `0001`–`0008`: autogenerate names revisions with a hex hash,
and `alembic history` is something a human reads during an incident.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_api_usage_logs"
down_revision: str | None = "0008_error_log"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "api_usage_logs",
        sa.Column("id", sa.Uuid(native_uuid=True), nullable=False),
        sa.Column("api_key_id", sa.String(length=64), nullable=True),
        sa.Column("organization_id", sa.String(length=256), nullable=False),
        sa.Column("endpoint", sa.String(length=256), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False),
        sa.Column("bytes_processed", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_api_usage_logs_api_key_id"), "api_usage_logs", ["api_key_id"], unique=False
    )
    op.create_index(
        op.f("ix_api_usage_logs_organization_id"),
        "api_usage_logs",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_api_usage_logs_endpoint"), "api_usage_logs", ["endpoint"], unique=False
    )
    op.create_index(
        op.f("ix_api_usage_logs_status_code"), "api_usage_logs", ["status_code"], unique=False
    )
    op.create_index(
        op.f("ix_api_usage_logs_timestamp"), "api_usage_logs", ["timestamp"], unique=False
    )
    op.create_index(
        op.f("ix_api_usage_logs_organization_id_timestamp"),
        "api_usage_logs",
        ["organization_id", "timestamp"],
        unique=False,
    )
    op.create_index(
        op.f("ix_api_usage_logs_api_key_id_timestamp"),
        "api_usage_logs",
        ["api_key_id", "timestamp"],
        unique=False,
    )


def downgrade() -> None:
    """Drops the table, and with it every record of what anyone consumed.

    Unlike `0008`'s, this downgrade destroys something commercial: usage that has not yet been
    invoiced exists nowhere else. Export it first if a real deployment ever runs this.

    Present because `alembic downgrade base` then `upgrade head` is how the drift check in
    `tests/test_db_persistence.py` proves this file and `app/db/models.py` agree.
    """
    op.drop_index(op.f("ix_api_usage_logs_api_key_id_timestamp"), table_name="api_usage_logs")
    op.drop_index(
        op.f("ix_api_usage_logs_organization_id_timestamp"), table_name="api_usage_logs"
    )
    op.drop_index(op.f("ix_api_usage_logs_timestamp"), table_name="api_usage_logs")
    op.drop_index(op.f("ix_api_usage_logs_status_code"), table_name="api_usage_logs")
    op.drop_index(op.f("ix_api_usage_logs_endpoint"), table_name="api_usage_logs")
    op.drop_index(op.f("ix_api_usage_logs_organization_id"), table_name="api_usage_logs")
    op.drop_index(op.f("ix_api_usage_logs_api_key_id"), table_name="api_usage_logs")
    op.drop_table("api_usage_logs")
