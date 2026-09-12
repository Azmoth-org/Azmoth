"""patient ziffer history — the Mengenbegrenzung ledger.

Revision ID: 0013_patient_ziffer_history
Revises: 0012_rule_proposals
Create Date: 2026-09-12

One table behind the Mengenbegrenzung constraint family — see `docs/content/
adr-002-complex-constraints.md`. Every other constraint the rules engine evaluates (an exclusion, a
Zielleistung, a factor cap) is decidable from a single invoice; "has this Ziffer already been billed
three times this quarter" is a fact about one patient *across* invoices, which is why it needs a
table at all rather than another CSV in `data/rules/` — see `app/db/models.py` for the reasoning in
full, on `PatientZifferHistoryRecord`.

Append-only, like `audit_events`: a row is evidence that a Ziffer was billed on a date, and the
`ON DELETE SET NULL` on `proposal_id` follows `audit_events.proposal_id` exactly, so the retention
purge can delete a draft without silently making a quantity cap unenforceable by erasing the
evidence that billing happened.

Written by hand for the same reasons as every other migration in this directory: autogenerate names
revisions with a hex hash where `alembic history` is something a human reads during an incident.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_patient_ziffer_history"
down_revision: str | None = "0012_rule_proposals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "patient_ziffer_history",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.String(length=256), nullable=False),
        sa.Column("patient_pseudonym", sa.String(length=128), nullable=False),
        sa.Column("ziffer", sa.String(length=16), nullable=False),
        sa.Column("service_date", sa.Date(), nullable=False),
        sa.Column("proposal_id", sa.Uuid(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["proposal_id"], ["proposals.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("patient_ziffer_history", schema=None) as batch_op:
        batch_op.create_index(
            "ix_patient_ziffer_history_lookup",
            ["organization_id", "patient_pseudonym", "ziffer", "service_date"],
            unique=False,
        )
        # `proposal_id` is `index=True` on the model, so a lookup that joins back to `proposals`
        # (an approval's audit trail — "which draft produced this occurrence") is not a table scan.
        batch_op.create_index(
            batch_op.f("ix_patient_ziffer_history_proposal_id"), ["proposal_id"], unique=False
        )


def downgrade() -> None:
    """Drops the table, and with it every recorded occurrence the Mengenbegrenzung check depends on.

    Present so `alembic downgrade base` then `upgrade head` can prove this file and
    `app/db/models.py` agree — not because running it against a working deployment is something
    anyone should do: downgrading this table means a quantity cap can no longer see any of a
    patient's earlier occurrences this quarter, silently widening what it will admit.
    """
    with op.batch_alter_table("patient_ziffer_history", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_patient_ziffer_history_proposal_id"))
        batch_op.drop_index("ix_patient_ziffer_history_lookup")
    op.drop_table("patient_ziffer_history")
