"""doctor_profiles and practices — who is billing, and from where.

Revision ID: 0005_practice_identity
Revises: 0004_actor_columns
Create Date: 2026-08-28

Two tables behind `POST /api/onboarding` in the web tier. They carry the business identity that
Better Auth deliberately does not:

    doctor_profiles     one row per `user.id`          — title, name, LANR, Facharzt
    practices           one row per `organization.id`  — practice name, BSNR, city, PLZ

**Why not columns on `user` and `organization`.** Those tables are Better Auth's. It creates and
alters them from the Next.js app (`pnpm --filter web auth:migrate`) by computing the schema from the
library's own field definitions, and `alembic/env.py` correspondingly excludes them from
autogenerate so this migrator never proposes dropping them. A `lanr` column added to `user` would
therefore be owned by neither: Alembic is told not to look at that table, and Better Auth's migrator
does not know the column exists. Two migrators can share one database only as long as their table
sets stay disjoint, so business data gets its own tables and the identity tier stays pure.

**No foreign keys into `user` or `organization`**, for the same reason `0004` added none: this
migration does not create those tables, and a constraint against something `alembic upgrade head`
cannot create would fail on every database where the engine runs without the web tier — the test
suite included. The ids are opaque and stable, which is all a join needs. What replaces the
constraint is the unique index on each id column, which is the property that actually matters: one
professional identity per account, one Betriebsstätte per organisation.

**`lanr` is unique and `bsnr` is not.** A LANR names a *person* and exists once, so two accounts
carrying one is either a duplicate registration or somebody typing a colleague's number — worth
refusing at sign-up rather than discovering in a rejected invoice. A BSNR names a *place*, and a
Berufsausübungsgemeinschaft where each physician has their own tenant is one place with several
organisations. Making the place unique would refuse that sign-up with an error nobody could act on.

**Nothing in the engine reads either table yet.** They live in this database rather than in one of
the web tier's own because they are business data and because the LANR and BSNR are what a PADnext
export will have to carry when invoice generation lands — at which point a second database would
make that a round-trip instead of a join. `apps/web/lib/db.ts` is how the web tier reaches them in
the meantime, on the same connection Better Auth already holds.

Written by hand for the same reasons as `0001`–`0004`: autogenerate names revisions with a hex hash
where `alembic history` is something a human reads during an incident.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_practice_identity"
down_revision: str | None = "0004_actor_columns"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "doctor_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.String(length=256), nullable=False),
        # The only nullable column here: a physician without an academic title is not an incomplete
        # record, and a NOT NULL would make them type a placeholder to get past the form.
        sa.Column("title", sa.String(length=64), nullable=True),
        sa.Column("first_name", sa.String(length=128), nullable=False),
        sa.Column("last_name", sa.String(length=128), nullable=False),
        sa.Column("lanr", sa.String(length=16), nullable=False),
        sa.Column("specialty", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("doctor_profiles", schema=None) as batch_op:
        # Unique because the onboarding endpoint upserts on it — `ON CONFLICT (user_id)` needs a
        # unique index to have a conflict target at all, on Postgres and on SQLite alike.
        batch_op.create_index(
            batch_op.f("ix_doctor_profiles_user_id"), ["user_id"], unique=True
        )
        # Unique because a LANR identifies one physician. See the module docstring.
        batch_op.create_index(batch_op.f("ix_doctor_profiles_lanr"), ["lanr"], unique=True)

    op.create_table(
        "practices",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.String(length=256), nullable=False),
        sa.Column("practice_name", sa.String(length=256), nullable=False),
        sa.Column("bsnr", sa.String(length=16), nullable=False),
        sa.Column("city", sa.String(length=128), nullable=False),
        # String, never an integer: a third of German PLZ begin with a zero.
        sa.Column("plz", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("practices", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_practices_organization_id"), ["organization_id"], unique=True
        )
        # Not unique — one Betriebsstätte, potentially several organisations. Indexed because
        # "which tenants bill from this BSNR" is the question a support case starts with.
        batch_op.create_index(batch_op.f("ix_practices_bsnr"), ["bsnr"], unique=False)


def downgrade() -> None:
    """Drops both tables, and with them every practice's billing identity.

    Like `0003`'s downgrade and unlike `0002`'s, this destroys something only a person can put back:
    a LANR and a BSNR are not recomputable from anything else in this database, so running it means
    every practice re-does onboarding. Present because a migration without a downgrade cannot be
    tested — `alembic downgrade base` then `upgrade head` is how the drift test proves this file and
    `app/db/models.py` agree — and not because it is something to run against a live database.

    Better Auth's `organization.name` keeps whatever the onboarding endpoint mirrored onto it. That
    is the correct asymmetry: the name is Better Auth's column, this migration never wrote it, and
    un-naming somebody's organisation is not this file's business.
    """
    with op.batch_alter_table("practices", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_practices_bsnr"))
        batch_op.drop_index(batch_op.f("ix_practices_organization_id"))
    op.drop_table("practices")

    with op.batch_alter_table("doctor_profiles", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_doctor_profiles_lanr"))
        batch_op.drop_index(batch_op.f("ix_doctor_profiles_user_id"))
    op.drop_table("doctor_profiles")
