"""proposals and the immutable audit log — the initial schema.

Revision ID: 0001_proposals_audit
Revises: None
Create Date: 2026-08-21

Two tables. `proposals` holds one row per solve plus the decision taken on it; `audit_events` is the
append-only log of what happened to each one. See `app/db/models.py` for what every column is for
and `docs/architecture/DATABASE.md` for the schema as a whole.

This file was produced by `alembic revision --autogenerate` and then edited, for two reasons worth
knowing about if you regenerate it:

1. Autogenerate emitted `postgresql.JSONB(astext_type=Text())` with `Text` unqualified and not
   imported — a `NameError` on import, on every dialect, before a single statement runs. It is
   `sa.Text()` below. Check for that in any regenerated migration that touches a JSONB column.
2. The revision id is a readable slug rather than a hex hash, because `alembic history` is something
   a human reads during an incident.

**What this migration deliberately does NOT do:** revoke UPDATE and DELETE on `audit_events`. The
table is append-only, and the application enforces that (`app/db/models.py::_reject_mutation`), but a
real deployment should also enforce it in the database:

    REVOKE UPDATE, DELETE ON audit_events FROM <application_role>;

That is left out of the migration on purpose. Alembic runs as the schema owner, and a grant made by
the owner against a role this file cannot know the name of would either fail or, worse, silently
apply to the wrong role. It belongs with the deployment's role definitions.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_proposals_audit"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _json() -> sa.types.TypeEngine:
    """JSONB on Postgres, portable JSON elsewhere — the same variant `app/db/base.py` declares.

    Spelled out here rather than imported from the app: a migration has to keep describing the
    schema it created even after the models move on, so it must not depend on their current shape.
    """
    return sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "proposals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("proposal_id", sa.String(length=64), nullable=False),
        sa.Column("case_id", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("receipt_hash", sa.String(length=64), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("catalog_version", sa.String(length=128), nullable=False),
        sa.Column("catalog_sha256", sa.String(length=64), nullable=False),
        sa.Column("rules_version", sa.String(length=128), nullable=False),
        sa.Column("rules_hash", sa.String(length=64), nullable=False),
        sa.Column("logic_version", sa.String(length=64), nullable=False),
        sa.Column("solver_version", sa.String(length=64), nullable=False),
        sa.Column("rules_engine_version", sa.String(length=64), nullable=False),
        sa.Column("solver_result_json", _json(), nullable=False),
        sa.Column("warnings_json", _json(), nullable=False),
        sa.Column("missing_documentation_json", _json(), nullable=False),
        sa.Column("rule_coverage_json", _json(), nullable=True),
        sa.Column("cached", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by", sa.String(length=256), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_by", sa.String(length=256), nullable=True),
        sa.Column("rejected_reason", sa.String(length=2048), nullable=True),
        sa.Column("exported_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("proposals", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_proposals_case_id"), ["case_id"], unique=False)
        # Unique: the public id is what the API and the frontend hold, so two rows answering to one
        # id would make "the proposal that was approved" ambiguous.
        batch_op.create_index(batch_op.f("ix_proposals_proposal_id"), ["proposal_id"], unique=True)
        batch_op.create_index(batch_op.f("ix_proposals_receipt_hash"), ["receipt_hash"], unique=False)
        batch_op.create_index(batch_op.f("ix_proposals_status"), ["status"], unique=False)
        batch_op.create_index(
            "ix_proposals_status_created_at", ["status", "created_at"], unique=False
        )

    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("proposal_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=16), nullable=False),
        sa.Column("actor", sa.String(length=256), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata_json", _json(), nullable=True),
        # CASCADE because an audit row pointing at a proposal that no longer exists is a record
        # nobody can interpret. No code path here deletes a proposal; retention is a policy decision.
        sa.ForeignKeyConstraint(["proposal_id"], ["proposals.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("audit_events", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_audit_events_event_type"), ["event_type"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_audit_events_proposal_id"), ["proposal_id"], unique=False
        )
        batch_op.create_index(
            "ix_audit_events_proposal_id_timestamp", ["proposal_id", "timestamp"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_audit_events_timestamp"), ["timestamp"], unique=False)


def downgrade() -> None:
    """Drops both tables — including the audit log.

    Present because a migration without a downgrade cannot be tested, and `alembic downgrade base`
    followed by `upgrade head` is how the drift test proves this file and `app/db/models.py` agree.
    Running it against a database holding real approvals destroys the record of them; that is what a
    downgrade of the *initial* migration means, and there is no version of it that does not.
    """
    with op.batch_alter_table("audit_events", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_audit_events_timestamp"))
        batch_op.drop_index("ix_audit_events_proposal_id_timestamp")
        batch_op.drop_index(batch_op.f("ix_audit_events_proposal_id"))
        batch_op.drop_index(batch_op.f("ix_audit_events_event_type"))
    op.drop_table("audit_events")

    with op.batch_alter_table("proposals", schema=None) as batch_op:
        batch_op.drop_index("ix_proposals_status_created_at")
        batch_op.drop_index(batch_op.f("ix_proposals_status"))
        batch_op.drop_index(batch_op.f("ix_proposals_receipt_hash"))
        batch_op.drop_index(batch_op.f("ix_proposals_proposal_id"))
        batch_op.drop_index(batch_op.f("ix_proposals_case_id"))
    op.drop_table("proposals")
