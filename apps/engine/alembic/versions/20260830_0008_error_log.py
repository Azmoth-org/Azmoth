"""error_log — one row per unhandled 5xx, so a pilot failure can be asked about.

Revision ID: 0008_error_log
Revises: 0007_api_keys_and_bulk_uploads
Create Date: 2026-08-30

The gap this closes is operational rather than functional. Before it, a user reporting "the upload
didn't work" left nothing to look at but whatever container log had not yet rotated, with no id to
search on and no way to tell whether it had happened to anyone else. That is survivable while the
only caller is us and unacceptable the moment a customer is on the other end.

    error_log      request_id, occurred_at, exception_type, message, route, method, org, api_key

**Only unanticipated failures.** A `422` for a malformed delivery or a `503` for a missing Soufflé
is the error contract working as designed; recording those would fill the table with noise and bury
the rows that mean something is broken. `app.api.errors.unhandled_error_handler` is the sole writer.

**No body, no headers, no traceback locals.** This engine handles billing data about identifiable
treatment, and a diagnostic table is the easiest place in a system for that to end up somewhere it
should not be. What is stored is enough to find the request in the logs and to ask the customer what
they were doing — and can therefore be read by whoever is on call rather than only by someone
cleared for patient data. The traceback stays in stdout.

**Not append-only**, unlike `audit_events`, and the difference is the same one `batch_jobs` draws:
nobody's liability attaches to a crash report. A retention policy that deletes rows older than N
days is a normal thing to want, and there is deliberately no constraint here that would prevent one.

The indexes serve the two questions anyone actually asks — "what has been failing lately"
(`occurred_at`, and the composite with `exception_type` to group it) and "did this customer hit
anything" (`organization_id`, `api_key_id`) — plus `request_id`, which is how a support
conversation starts: somebody quotes the id from their `500` response.

Written by hand for the same reason as `0001`–`0007`: autogenerate names revisions with a hex hash,
and `alembic history` is something a human reads during an incident.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_error_log"
down_revision: str | None = "0007_api_keys_and_bulk_uploads"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "error_log",
        sa.Column("id", sa.Uuid(native_uuid=True), nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("exception_type", sa.String(length=128), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("http_route", sa.String(length=256), nullable=True),
        sa.Column("http_method", sa.String(length=8), nullable=True),
        sa.Column("organization_id", sa.String(length=256), nullable=True),
        sa.Column("api_key_id", sa.String(length=64), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_error_log_request_id"), "error_log", ["request_id"], unique=False)
    op.create_index(op.f("ix_error_log_occurred_at"), "error_log", ["occurred_at"], unique=False)
    op.create_index(
        op.f("ix_error_log_exception_type"), "error_log", ["exception_type"], unique=False
    )
    op.create_index(op.f("ix_error_log_http_route"), "error_log", ["http_route"], unique=False)
    op.create_index(
        op.f("ix_error_log_organization_id"), "error_log", ["organization_id"], unique=False
    )
    op.create_index(op.f("ix_error_log_api_key_id"), "error_log", ["api_key_id"], unique=False)
    op.create_index(
        op.f("ix_error_log_occurred_at_exception_type"),
        "error_log",
        ["occurred_at", "exception_type"],
        unique=False,
    )


def downgrade() -> None:
    """Drops the table. Loses crash reports and nothing a customer relies on.

    The one downgrade in this history that is genuinely safe to run: no other table references it,
    nothing reads it in a request path, and what it holds is diagnostic rather than contractual.
    Present, like the others, because `alembic downgrade base` then `upgrade head` is how the drift
    check in `tests/test_db_persistence.py` proves this file and `app/db/models.py` agree.
    """
    op.drop_index(op.f("ix_error_log_occurred_at_exception_type"), table_name="error_log")
    op.drop_index(op.f("ix_error_log_api_key_id"), table_name="error_log")
    op.drop_index(op.f("ix_error_log_organization_id"), table_name="error_log")
    op.drop_index(op.f("ix_error_log_http_route"), table_name="error_log")
    op.drop_index(op.f("ix_error_log_exception_type"), table_name="error_log")
    op.drop_index(op.f("ix_error_log_occurred_at"), table_name="error_log")
    op.drop_index(op.f("ix_error_log_request_id"), table_name="error_log")
    op.drop_table("error_log")
