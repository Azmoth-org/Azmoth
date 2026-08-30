"""api_keys, and the upload path that makes a bulk job resumable.

Revision ID: 0007_api_keys_and_bulk_uploads
Revises: 0006_organization_scope
Create Date: 2026-08-30

Two changes, both in service of the commercial API surface (`/api/v1/audit/*`).

    api_keys                    one row per credential issued to a practice
    batch_jobs.upload_path      where a bulk job's ZIP is, so a restart can resume it

**`api_keys` stores no secret.** `key_hash` is SHA-256 over the token; the token itself is returned
once, by the endpoint that mints it, and exists nowhere in this database. A dump of this table is
therefore not a set of credentials — it is a set of *identifiers* — which is the property that lets
it live in the same Postgres as everything else without a separate secret store.

`key_id` is the public prefix and it carries two indexes' worth of work on its own: `unique=True`
makes the per-request lookup a single indexed read (rather than hashing every row in the table to
find a match), and it is the handle a caller passes to revoke a key and the label a log line uses.
`key_hash` is indexed as well, deliberately, because it is the second half of that lookup's
predicate and a deployment that ever needs to answer "is this exact token known" without the prefix
should not have to scan.

**No foreign key into `organization`.** The same reason as `0004`, `0005` and `0006`: that table
belongs to Better Auth's own migrator, `alembic upgrade head` does not create it, and a constraint
here would make the schema unappliable wherever the engine runs alone — the test suite included.
Unlike `proposals.organization_id`, though, this column is `NOT NULL`: there are no legacy rows to
accommodate, and a key that named no tenant would authenticate a caller into nothing while looking
like it had worked.

**Revocation is a column, not a `DELETE`.** `revoked_at` is set and the row stays. "This key was
live from March to July" is a question a billing dispute asks, and a deleted row cannot answer it.
Verification refuses a revoked key, so the caller sees a real deletion either way.

**`batch_jobs.upload_path` is nullable and always will be.** It distinguishes the two ways a batch
can arrive rather than recording something every batch has: `POST /api/v1/padnext/batch` holds its
files in memory and writes nothing to disk, so its rows have no path and cannot be resumed after a
restart; `POST /api/v1/audit/bulk` writes the archive first, so its rows can. The startup recovery
branches on exactly this being non-null — see
`app.services.batch_audit.BatchAuditService.reap_interrupted_batches`. A `NOT NULL` here would be
wrong rather than merely premature.

No index on it. Nothing looks a job up *by* path; the one query that reads it
(`WHERE status IN (…) AND upload_path IS NOT NULL`) is already served by `ix_batch_jobs_status_…`
and touches a handful of rows at startup.

Written by hand for the same reason as `0001`–`0006`: autogenerate names revisions with a hex hash,
and `alembic history` is something a human reads during an incident.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_api_keys_and_bulk_uploads"
down_revision: str | None = "0006_organization_scope"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "api_keys",
        sa.Column("id", sa.Uuid(native_uuid=True), nullable=False),
        sa.Column("key_id", sa.String(length=64), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("organization_id", sa.String(length=256), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("created_by", sa.String(length=256), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_api_keys_key_id"), "api_keys", ["key_id"], unique=True)
    op.create_index(op.f("ix_api_keys_key_hash"), "api_keys", ["key_hash"], unique=False)
    op.create_index(
        op.f("ix_api_keys_organization_id"), "api_keys", ["organization_id"], unique=False
    )
    op.create_index(
        op.f("ix_api_keys_organization_id_created_at"),
        "api_keys",
        ["organization_id", "created_at"],
        unique=False,
    )

    # `batch_alter_table` for the same reason as `0006`: SQLite cannot ADD COLUMN with every
    # option in one statement, so Alembic's batch mode rewrites the table. On Postgres it emits
    # the plain ALTER.
    with op.batch_alter_table("batch_jobs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("upload_path", sa.Text(), nullable=True))


def downgrade() -> None:
    """Drops the table, and with it every issued credential.

    Not reversible in any sense that matters: the tokens were never stored, so re-running the
    upgrade gives an empty table and every integration that was working stops. Present because a
    migration without a downgrade cannot be tested — `alembic downgrade base` then `upgrade head`
    is how the drift check in `tests/test_db_persistence.py` proves this file and
    `app/db/models.py` agree — and not because it is something to run against a live deployment.

    Dropping `upload_path` additionally orphans whatever ZIPs are on disk under `UPLOAD_DIR`: the
    rows that named them are the only index of that directory. Clean it up by hand if you run this.
    """
    with op.batch_alter_table("batch_jobs", schema=None) as batch_op:
        batch_op.drop_column("upload_path")

    op.drop_index(op.f("ix_api_keys_organization_id_created_at"), table_name="api_keys")
    op.drop_index(op.f("ix_api_keys_organization_id"), table_name="api_keys")
    op.drop_index(op.f("ix_api_keys_key_hash"), table_name="api_keys")
    op.drop_index(op.f("ix_api_keys_key_id"), table_name="api_keys")
    op.drop_table("api_keys")
