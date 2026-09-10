"""rule proposals — a pilot's report that a Ziffer has no rule at all.

Revision ID: 0012_rule_proposals
Revises: 0011_retention_purge
Create Date: 2026-09-10

One table behind `POST /api/v1/rules/proposals`. It is a demand signal, not a verdict: a pilot
practice hitting a Ziffer this engine has no rule for at all, reported from the audit report they
were looking at. It is unrelated to `rule_reviews` (a verdict on a rule that already exists) and
unrelated to `proposals` (the billing-draft lifecycle) despite the name — see `app/db/models.py`
for why neither existing table fits and a new one was written instead of a migration onto either.

No status, no workflow, no foreign key on `ziffer` — a Ziffer names a position in the GOÄ catalog,
which is versioned source data outside this database, same reasoning as `rule_reviews.rule_id`.

Written by hand for the same reasons as every other migration in this directory: autogenerate names
revisions with a hex hash where `alembic history` is something a human reads during an incident.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_rule_proposals"
down_revision: str | None = "0011_retention_purge"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "rule_proposals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ziffer", sa.String(length=16), nullable=False),
        sa.Column("context", sa.String(length=500), nullable=False),
        sa.Column("receipt_hash", sa.String(length=64), nullable=True),
        sa.Column("organization_id", sa.String(length=256), nullable=False),
        sa.Column("created_by", sa.String(length=256), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("rule_proposals", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_rule_proposals_ziffer"), ["ziffer"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_rule_proposals_receipt_hash"), ["receipt_hash"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_rule_proposals_created_by"), ["created_by"], unique=False
        )
        batch_op.create_index(
            "ix_rule_proposals_organization_id_created_at",
            ["organization_id", "created_at"],
            unique=False,
        )


def downgrade() -> None:
    """Drops the table, and with it every report a pilot filed about a missing rule.

    Present so `alembic downgrade base` then `upgrade head` can prove this file and
    `app/db/models.py` agree — not because running it against a working deployment is something
    anyone should do: the whole point of the table is to accumulate demand data over time.
    """
    with op.batch_alter_table("rule_proposals", schema=None) as batch_op:
        batch_op.drop_index("ix_rule_proposals_organization_id_created_at")
        batch_op.drop_index(batch_op.f("ix_rule_proposals_created_by"))
        batch_op.drop_index(batch_op.f("ix_rule_proposals_receipt_hash"))
        batch_op.drop_index(batch_op.f("ix_rule_proposals_ziffer"))
    op.drop_table("rule_proposals")
