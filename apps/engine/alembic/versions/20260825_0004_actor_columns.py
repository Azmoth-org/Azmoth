"""created_by on proposals and batch_jobs — the authenticated user behind a record.

Revision ID: 0004_actor_columns
Revises: 0003_rule_reviews
Create Date: 2026-08-25

The web tier now holds a Better Auth session and forwards the signed-in user's id to this service
in `X-User-ID` (see `app/api/identity.py`). Two things then have somewhere to be written:

    proposals.created_by    who ran the solve that produced this draft
    batch_jobs.created_by   who uploaded this batch

`audit_events.actor` needed no change — it has been there since `0001` and simply stops saying
`anonymous` for calls that arrive through the UI. What it could not answer is the *queryable*
question: "every draft this user produced" is a filter on the proposals table, and scanning an
append-only log for `CREATED` rows to answer it would be the wrong shape for the one query a
data-subject request actually asks. Hence a column, and hence the index on it.

**Nullable, with no backfill.** Every row written before this migration was produced by a service
that had no idea who was calling. `server_default='system'` would stamp a plausible-looking answer
onto history, which is the one option worse than admitting the gap — the same reasoning that makes
`ANONYMOUS_ACTOR` a conspicuous value rather than a name. New rows always carry a value: the API
passes `system` or `anonymous` when no session travelled.

**No foreign key to `user`.** That table belongs to Better Auth, which creates and migrates it from
the Next.js app (`pnpm --filter web auth:migrate`). A constraint here would make this schema depend
on a table `alembic upgrade head` does not create, and would fail against any database where the
engine runs without the web tier — the test suite included. The id is opaque and stable, which is
all a join needs. `alembic/env.py` correspondingly excludes Better Auth's tables from autogenerate,
so a `--autogenerate` run against the shared database never proposes dropping them.

Written by hand for the same reasons as `0001`–`0003`: autogenerate names revisions with a hex hash
where `alembic history` is something a human reads during an incident.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_actor_columns"
down_revision: str | None = "0003_rule_reviews"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("proposals", schema=None) as batch_op:
        batch_op.add_column(sa.Column("created_by", sa.String(length=256), nullable=True))
        batch_op.create_index(batch_op.f("ix_proposals_created_by"), ["created_by"], unique=False)

    with op.batch_alter_table("batch_jobs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("created_by", sa.String(length=256), nullable=True))
        batch_op.create_index(batch_op.f("ix_batch_jobs_created_by"), ["created_by"], unique=False)


def downgrade() -> None:
    """Drops both columns, and with them the only record of who produced each row.

    Unlike `0003`'s downgrade this destroys nothing a person wrote by hand — the same attribution
    is still in `audit_events.actor` for proposals, which this migration does not touch. Batches
    have no audit log, so for those it is genuinely lost. Present because a migration without a
    downgrade cannot be tested: `alembic downgrade base` then `upgrade head` is how the drift test
    proves this file and `app/db/models.py` agree.
    """
    with op.batch_alter_table("batch_jobs", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_batch_jobs_created_by"))
        batch_op.drop_column("created_by")

    with op.batch_alter_table("proposals", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_proposals_created_by"))
        batch_op.drop_column("created_by")
