"""audit_events survives the deletion of its proposal — the schema half of the retention purge.

Revision ID: 0011_retention_purge
Revises: 0010_subscriptions_and_invoices
Create Date: 2026-09-06

`0001` created `audit_events.proposal_id` with `ON DELETE CASCADE` and said why:

    CASCADE because an audit row pointing at a proposal that no longer exists is a record nobody
    can interpret. No code path here deletes a proposal; retention is a policy decision.

Both halves were true when they were written. `scripts/purge_old_data.py` makes the second one
false, and the moment it does, the first becomes actively dangerous: every purge would delete the
log of what was approved, by whom and when, along with the proposal — destroying exactly the
evidence that DSGVO Art. 5 Abs. 2 requires the operator to be able to produce. A deletion nobody can
demonstrate happened is, for accountability purposes, indistinguishable from data loss.

So this migration answers the interpretability objection a different way instead of accepting the
cascade:

    audit_events   + target_id (the `prop_<hex>` handle, denormalised, NOT NULL, backfilled)
                   proposal_id  NOT NULL → NULLABLE
                   FK           ON DELETE CASCADE → ON DELETE SET NULL

`target_id` is a copy rather than a join, and that is the whole point of it: every other way of
naming the proposal is a foreign key, and a foreign key is by definition emptied when its target
goes. After a purge the row reads "APPROVED, prop_a1b2c3d4, by user_x, at T" with a null
`proposal_id` — self-contained, and interpretable precisely because the handle is a value.

The handle rather than the surrogate `proposals.id`, because the handle is the identifier that
appears in a receipt, in an export and in the API a Rechnungsprüfer was shown. It is what an outside
question arrives already phrased in.

**The backfill is the reason this is not two lines.** Existing rows have no `target_id`, and adding
the column `NOT NULL` without one would fail on any non-empty table. It is added nullable, filled
from the join while the join still resolves — which is now, and never again for a purged row — and
only then tightened. A row whose join does not resolve gets the literal `ORPHANED`: that can only
happen where foreign key integrity was already broken (SQLite enforces FKs only when
`PRAGMA foreign_keys=ON`), and a greppable marker on a handful of rows is a better outcome than a
migration that aborts a deploy over damage done long ago.

**Why the dialect branch.** SQLite cannot alter a column's nullability or a constraint's referential
action at all; Alembic's batch mode rebuilds the table instead, and rebuilding needs the FK to carry
a name it can drop. Postgres does the real `ALTER` and the constraint it is dropping is the one
`0001` created unnamed, which Postgres named `audit_events_proposal_id_fkey` by its own convention.
The two paths are genuinely different statements, so they are written as two functions rather than
as one with conditionals threaded through it.

**`ON DELETE SET NULL` and the REVOKE in `0001`'s docstring.** A deployment that follows that advice
(`REVOKE UPDATE, DELETE ON audit_events FROM <application_role>`) does not break this: a referential
action is performed by the system, not by the deleting role, and is not checked against that role's
column privileges. The application still cannot issue an `UPDATE` of its own, which is what the
REVOKE is for, and the append-only guards in `app/db/models.py` still refuse one at the ORM level.

Written by hand for the same reason as `0001`–`0010`: autogenerate names revisions with a hex hash,
and `alembic history` is something a human reads during an incident.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_retention_purge"
down_revision: str | None = "0010_subscriptions_and_invoices"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The name this migration gives the foreign key on both dialects, so that a later migration has one
#: name to drop rather than a dialect-dependent guess. `0001` created it unnamed.
FK_NAME = "fk_audit_events_proposal_id_proposals"

#: What Postgres called that unnamed constraint: `<table>_<column>_fkey`.
PG_ORIGINAL_FK = "audit_events_proposal_id_fkey"

#: Stands in for a handle that could not be resolved. See the module docstring.
ORPHAN_MARKER = "ORPHANED"


def _audit_events_before() -> sa.Table:
    """The table as it stands *before* this migration, for SQLite's batch rebuild.

    Alembic applies the batch operations to this definition to derive the new table, so it has to
    describe what is there now — including `target_id`, which `upgrade` has already added by the
    time the rebuild runs. Spelled out rather than reflected because the foreign key must carry
    `FK_NAME` for `drop_constraint` to have something to name; reflection would hand back the
    unnamed one `0001` created.

    **The four indexes from `0001` are part of "what is there now" and have to be listed.** A batch
    rebuild creates the new table from this definition alone: an index omitted here is an index the
    table comes back without, silently, with nothing failing until a query that needed it is slow in
    production. That is what the schema drift test in `tests/test_db_persistence.py` caught.
    """
    metadata = sa.MetaData()
    table = sa.Table(
        "audit_events",
        metadata,
        sa.Column("id", sa.Uuid(native_uuid=True), nullable=False),
        sa.Column("proposal_id", sa.Uuid(native_uuid=True), nullable=False),
        sa.Column("target_id", sa.String(length=64), nullable=True),
        sa.Column("event_type", sa.String(length=16), nullable=False),
        sa.Column("actor", sa.String(length=256), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(
            ["proposal_id"], ["proposals.id"], name=FK_NAME, ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    sa.Index("ix_audit_events_event_type", table.c.event_type)
    sa.Index("ix_audit_events_proposal_id", table.c.proposal_id)
    sa.Index("ix_audit_events_timestamp", table.c.timestamp)
    sa.Index("ix_audit_events_proposal_id_timestamp", table.c.proposal_id, table.c.timestamp)
    return table


def upgrade() -> None:
    # 1. The column, nullable for now — a NOT NULL add would fail on any table with rows in it.
    with op.batch_alter_table("audit_events", schema=None) as batch_op:
        batch_op.add_column(sa.Column("target_id", sa.String(length=64), nullable=True))

    # 2. Fill it from the join, while the join still resolves. This is the only moment it can be
    #    done: after a purge the proposal is gone and the handle is unrecoverable from anywhere.
    op.execute(
        sa.text(
            "UPDATE audit_events SET target_id = ("
            "  SELECT proposals.proposal_id FROM proposals"
            "  WHERE proposals.id = audit_events.proposal_id"
            ")"
        )
    )
    # An audit row whose proposal was already missing — only reachable if FK enforcement was off.
    op.execute(
        sa.text("UPDATE audit_events SET target_id = :marker WHERE target_id IS NULL").bindparams(
            marker=ORPHAN_MARKER
        )
    )

    # 3. Tighten the column and swap the referential action.
    if op.get_bind().dialect.name == "sqlite":
        _upgrade_sqlite()
    else:
        _upgrade_standard()

    # 4. "Everything that ever happened to prop_abc123", asked after the proposal is gone. Created
    #    outside the rebuild so both dialects take the same path to it.
    op.create_index(
        op.f("ix_audit_events_target_id_timestamp"),
        "audit_events",
        ["target_id", "timestamp"],
        unique=False,
    )


def _upgrade_standard() -> None:
    """Postgres and anything else that can alter a column and a constraint in place."""
    op.alter_column(
        "audit_events", "target_id", existing_type=sa.String(length=64), nullable=False
    )
    op.alter_column(
        "audit_events",
        "proposal_id",
        existing_type=sa.Uuid(native_uuid=True),
        nullable=True,
    )
    op.drop_constraint(PG_ORIGINAL_FK, "audit_events", type_="foreignkey")
    op.create_foreign_key(
        FK_NAME, "audit_events", "proposals", ["proposal_id"], ["id"], ondelete="SET NULL"
    )


def _upgrade_sqlite() -> None:
    """SQLite: Alembic rebuilds the table, because none of the three changes exist as an `ALTER`."""
    with op.batch_alter_table(
        "audit_events", schema=None, copy_from=_audit_events_before()
    ) as batch_op:
        batch_op.alter_column(
            "target_id", existing_type=sa.String(length=64), nullable=False
        )
        batch_op.alter_column(
            "proposal_id", existing_type=sa.Uuid(native_uuid=True), nullable=True
        )
        batch_op.drop_constraint(FK_NAME, type_="foreignkey")
        batch_op.create_foreign_key(
            FK_NAME, "proposals", ["proposal_id"], ["id"], ondelete="SET NULL"
        )


def downgrade() -> None:
    """Restores the cascade — and deletes every audit row belonging to a purged proposal.

    Not a symmetric revert, and the asymmetry is the interesting part. `proposal_id` has to become
    `NOT NULL` again, and the rows that cannot satisfy that are exactly the ones the purge preserved:
    the record of proposals that no longer exist. There is nothing to put back in the column, so they
    are deleted. That is the pre-`0011` behaviour faithfully restored, which is what a downgrade is
    for, and it destroys evidence a data protection authority may ask for, which is what running one
    on a live deployment means here.

    Present because a migration without a downgrade cannot be tested — `alembic downgrade base` then
    `upgrade head` is how `tests/test_db_persistence.py` proves this file and `app/db/models.py`
    agree. Not because it is something to run.
    """
    op.drop_index(op.f("ix_audit_events_target_id_timestamp"), table_name="audit_events")

    op.execute(sa.text("DELETE FROM audit_events WHERE proposal_id IS NULL"))

    if op.get_bind().dialect.name == "sqlite":
        after = _audit_events_before()
        after.c.proposal_id.nullable = True
        after.c.target_id.nullable = False
        with op.batch_alter_table("audit_events", schema=None, copy_from=after) as batch_op:
            batch_op.alter_column(
                "proposal_id", existing_type=sa.Uuid(native_uuid=True), nullable=False
            )
            batch_op.drop_constraint(FK_NAME, type_="foreignkey")
            batch_op.create_foreign_key(
                FK_NAME, "proposals", ["proposal_id"], ["id"], ondelete="CASCADE"
            )
            batch_op.drop_column("target_id")
        return

    op.drop_constraint(FK_NAME, "audit_events", type_="foreignkey")
    op.create_foreign_key(
        PG_ORIGINAL_FK, "audit_events", "proposals", ["proposal_id"], ["id"], ondelete="CASCADE"
    )
    op.alter_column(
        "audit_events",
        "proposal_id",
        existing_type=sa.Uuid(native_uuid=True),
        nullable=False,
    )
    op.drop_column("audit_events", "target_id")
