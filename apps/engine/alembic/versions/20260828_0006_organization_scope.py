"""organization_id on proposals and batch_jobs — the tenancy boundary, in the schema.

Revision ID: 0006_organization_scope
Revises: 0005_practice_identity
Create Date: 2026-08-28

Until now an organisation was something the UI *displayed*. `0005` gave a practice its own row and
the rail its name, and the note on `organization()` in `apps/web/lib/auth.ts` was explicit that this
was "the identity half of multi-tenancy landing before the authorisation half, not multi-tenancy".
This is the other half: the column every proposal and batch query now filters on, so one practice
cannot read, approve or export another's records.

    proposals.organization_id    the Better Auth `organization.id` a draft belongs to
    batch_jobs.organization_id   the same, for a PADnext batch upload

`batch_files` gets no column of its own. A file is reachable only through its batch — the FK is
`ON DELETE CASCADE` and there is no endpoint that reads one by id — so scoping the parent scopes the
child, and a second copy of the tenant on every file row would be a fact with two places to
disagree with itself.

**No foreign key into `organization`**, for the same reason `0004` and `0005` added none: that table
is Better Auth's and is created by the Next.js app's own migrator, so a constraint here would make
`alembic upgrade head` fail on every database where the engine runs without the web tier — the test
suite included. What the id has to be is opaque and stable, which is all a filter needs.

**Nullable, and the nullability is about history, not about policy.** Rows written before this
column existed have no organisation and none can be invented for them: a backfill would have to
guess which practice a draft belonged to, and guessing wrong files somebody's billing record under a
stranger's tenant. So legacy rows keep `NULL` — and because the enforcement is an equality filter
(`organization_id == :org`), `NULL` matches no tenant at all. A legacy row is therefore *unreachable*
through the API rather than *visible to everyone*, which is the direction that ambiguity has to fail
in. New rows always carry a value: `app.api.tenancy` refuses a write whose request had no
`X-Organization-ID` header before it reaches a store, so there is no code path that inserts a NULL.

A `NOT NULL` constraint is therefore the right end state and is deliberately not set here — it
cannot be, while rows exist that would violate it. Closing it is a two-step that belongs to a
deployment rather than to this file: decide what happens to the legacy rows (assign, or delete under
a retention policy), then a migration that sets `NOT NULL`. Written down here because a nullable
column with no note is how "temporary" becomes permanent.

**The indexes are tenant-leading composites, not plain indexes on the column.** Every listing is now
`WHERE organization_id = ? ORDER BY created_at DESC`, so `(organization_id, created_at)` serves both
halves of the actual query; a plain index on `organization_id` would be redundant with it, since a
composite's leading column already serves an equality lookup on its own. The existing
`(status, created_at)` indexes stay — they still serve the status-filtered listing, now as a second
filter step.

Written by hand for the same reason as `0001`–`0005`: autogenerate names revisions with a hex hash,
and `alembic history` is something a human reads during an incident.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_organization_scope"
down_revision: str | None = "0005_practice_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # `batch_alter_table` on both, because SQLite cannot ADD COLUMN with every option in one
    # statement and Alembic's batch mode rewrites the table instead. On Postgres it emits the plain
    # ALTER; the suite runs SQLite, so both paths have to work from one file.
    with op.batch_alter_table("proposals", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("organization_id", sa.String(length=256), nullable=True)
        )
        batch_op.create_index(
            batch_op.f("ix_proposals_organization_id_created_at"),
            ["organization_id", "created_at"],
            unique=False,
        )

    with op.batch_alter_table("batch_jobs", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("organization_id", sa.String(length=256), nullable=True)
        )
        batch_op.create_index(
            batch_op.f("ix_batch_jobs_organization_id_created_at"),
            ["organization_id", "created_at"],
            unique=False,
        )


def downgrade() -> None:
    """Drops both columns, and with them the only record of which practice owns which draft.

    Unlike `0002`'s downgrade this destroys something that cannot be recomputed: the organisation a
    proposal was created under exists nowhere else in this database. Running it against a live
    multi-tenant deployment does not merely revert a feature, it merges every tenant's records into
    one undifferentiated table — and the upgrade cannot separate them again.

    Present because a migration without a downgrade cannot be tested: `alembic downgrade base` then
    `upgrade head` is how the drift test in `tests/test_db_persistence.py` proves this file and
    `app/db/models.py` agree. Not because it is something to run.
    """
    with op.batch_alter_table("batch_jobs", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_batch_jobs_organization_id_created_at"))
        batch_op.drop_column("organization_id")

    with op.batch_alter_table("proposals", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_proposals_organization_id_created_at"))
        batch_op.drop_column("organization_id")
