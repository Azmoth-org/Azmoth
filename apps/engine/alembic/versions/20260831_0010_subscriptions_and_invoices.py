"""Subscriptions, quotas and priced periods — the schema an API can be sold on.

Revision ID: 0010_subscriptions_and_invoices
Revises: 0009_api_usage_logs
Create Date: 2026-08-31

`0009` made the API meterable. This makes it **chargeable**, which needs three things it did not
have: a billable unit, an entitlement to check that unit against, and somewhere to put what a period
came to.

    api_usage_logs.invoices_processed   the billable unit, per request
    organization_billing                which plan a practice is on, and what it promised them
    billing_invoices                    one row per closed period, priced, in euro cents

## The billable unit, and why `request_count` was not one

`request_count` cannot be invoiced. One `POST /audit/single` is one invoice and one
`POST /audit/bulk` may be five hundred, so a price per request charges the same work differently
depending on how a partner chose to batch it — which is a pricing bug that presents as a customer
arguing, correctly, that they were overcharged for using the endpoint we told them to use.
`bytes_processed` is no better: an archive's size describes its compression.

So the column counts what the engine actually did. It is `NOT NULL DEFAULT 0`, and every row written
before this migration therefore reads as zero rather than as null — which is the honest value. Those
requests were metered before there was a unit to attribute to them, and backfilling a guess into a
column an invoice is built from would be inventing history.

## Why `subscription_tier` is not a column on `organization`

Because that table is not ours. Better Auth computes its schema from the library's own field
definitions and creates it from the web tier (`pnpm --filter web auth:migrate`); `alembic/env.py`
names `organization` in the denylist precisely so autogenerate cannot offer to drop it. A billing
column added there would be owned by neither migrator and dropped by the next Better Auth upgrade.

It is also unreadable from where it is needed. The quota is enforced in the **engine**, on both
audit paths, and the engine deliberately cannot query Better Auth's tables — `app/api/tenancy.py`
explains at length why it does not even check that an organisation exists. An entitlement consulted
before every audit has to live in a table Alembic owns, keyed by the organisation id.

`doctor_profiles` and `practices` are here for the same reason, reached from the identity side.

## Why the plan's numbers are copied onto the assignment

`organization_billing` stores `monthly_invoice_quota`, `overage_rate_cents` and `allow_overage`
alongside `plan_code`, duplicating what `app/services/billing_plans.py` already says. The
duplication is the feature: a practice's quota is what was agreed when they were put on the plan,
and no later edit to the catalog, no rollback to an older deployment and no removed plan can change
it retroactively. The catalog is where a *new* assignment gets its numbers; the row is where an
existing one keeps them.

## Two constraints worth naming

`organization_billing.organization_id` is **unique**. One practice, one plan — and the index is what
makes get-or-create safe: two simultaneous first audits race, one loses, and both then read the same
row instead of creating two entitlements that would each count half the traffic.

`billing_invoices (organization_id, period_start)` is **unique**, and that constraint *is* the
idempotency of closing a period. A retry after a timeout is normal; double-charging a customer is
not, so the second attempt loses on the index rather than inserting a duplicate.

## No foreign keys into Better Auth's tables

Same reasoning as `api_keys`, `api_usage_logs` and every other organisation id in this schema:
`alembic upgrade head` does not create `organization`, so a constraint on it would make the schema
unappliable wherever the engine runs alone — which is how the whole test suite runs it.

## Why every step here checks before it acts

This migration is **idempotent**, which no other migration in this history is, and that is a repair
rather than a style. `DATABASE_AUTO_CREATE` defaults to true and `app/db/session.py::init_models`
only refused it under `APP_ENV=production` — so a developer who pointed a laptop at the deployed
Neon database ran `Base.metadata.create_all` against it. `create_all` is `CREATE TABLE IF NOT
EXISTS` over the whole of `app/db/models.py`: it skipped `api_usage_logs`, which already existed at
`0009`, and created `organization_billing` and `billing_invoices`, which did not — without touching
`alembic_version`. The next deploy then ran `upgrade head`, reached this file, added
`invoices_processed` cleanly and died on `DuplicateTableError: relation "organization_billing"
already exists`.

The guard in `init_models` is now on the *database* rather than on `APP_ENV`, so that cannot recur
(a Postgres URL is Alembic's, in every environment). This file stays checked anyway, because the
databases that were already damaged that way have to be able to migrate through it. The checks are
per-object, not one big "does the table exist" around the whole function: `create_all` leaves
exactly the mixed state — two tables present, one column absent — that an all-or-nothing guard gets
wrong in both directions.

`downgrade` is guarded the same way, so a database in that mixed state can be unwound rather than
only migrated forward.

Written by hand for the same reason as `0001`–`0009`: autogenerate names revisions with a hex hash,
and `alembic history` is something a human reads during an incident.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_subscriptions_and_invoices"
down_revision: str | None = "0009_api_usage_logs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# --------------------------------------------------------------------------------------------
# Reflection helpers. See the module docstring for why this migration, alone in this history,
# checks before it acts.
# --------------------------------------------------------------------------------------------
#
# A fresh `sa.inspect()` per call rather than one cached inspector: an Inspector memoises what it
# reflected, so one built before `create_table` still reports the table as absent afterwards — and
# every one of these is asked *between* DDL statements. Reflection is cheap; a stale answer here
# costs a failed deploy.


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _has_table(table: str) -> bool:
    return table in _inspector().get_table_names()


def _has_column(table: str, column: str) -> bool:
    return any(existing["name"] == column for existing in _inspector().get_columns(table))


def _has_index(table: str, index: str) -> bool:
    """Whether `index` exists on `table`. False for a table that is not there at all."""
    if not _has_table(table):
        return False
    return any(existing["name"] == index for existing in _inspector().get_indexes(table))


def _ensure_index(index: str, table: str, columns: list[str], *, unique: bool) -> None:
    """`CREATE INDEX IF NOT EXISTS`, by name.

    By name and not by column set, deliberately: `billing_invoices` carries a unique and a
    non-unique index over the same two columns, and a column-set comparison would see the first as
    satisfying the second.
    """
    if not _has_index(table, index):
        op.create_index(index, table, columns, unique=unique)


def _drop_index_if_exists(index: str, table: str) -> None:
    if _has_index(table, index):
        op.drop_index(index, table_name=table)


def upgrade() -> None:
    # ------------------------------------------------------------------------------------------
    # 1. the billable unit
    # ------------------------------------------------------------------------------------------
    # `server_default="0"` and not merely a Python-side default: this is an ALTER on a table that
    # may already hold rows, and Postgres needs a value for them. The server default is dropped
    # immediately afterwards so the column matches `app/db/models.py`, where the default is
    # application-side — the same discipline `utcnow` follows, and what keeps the drift check in
    # `tests/test_db_persistence.py` honest.
    if not _has_column("api_usage_logs", "invoices_processed"):
        op.add_column(
            "api_usage_logs",
            sa.Column("invoices_processed", sa.Integer(), nullable=False, server_default="0"),
        )
        with op.batch_alter_table("api_usage_logs") as batch:
            batch.alter_column("invoices_processed", server_default=None)

    # ------------------------------------------------------------------------------------------
    # 2. the entitlement
    # ------------------------------------------------------------------------------------------
    if not _has_table("organization_billing"):
        _create_organization_billing()
    _ensure_organization_billing_indexes()

    # ------------------------------------------------------------------------------------------
    # 3. what a closed period came to
    # ------------------------------------------------------------------------------------------
    if not _has_table("billing_invoices"):
        _create_billing_invoices()
    _ensure_billing_invoices_indexes()


def _create_organization_billing() -> None:
    op.create_table(
        "organization_billing",
        sa.Column("id", sa.Uuid(native_uuid=True), nullable=False),
        sa.Column("organization_id", sa.String(length=256), nullable=False),
        sa.Column("subscription_tier", sa.String(length=32), nullable=False),
        sa.Column("plan_code", sa.String(length=64), nullable=False),
        sa.Column("monthly_invoice_quota", sa.Integer(), nullable=False),
        sa.Column("overage_rate_cents", sa.Integer(), nullable=False),
        sa.Column("allow_overage", sa.Boolean(), nullable=False),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def _ensure_organization_billing_indexes() -> None:
    _ensure_index(
        op.f("ix_organization_billing_organization_id"),
        "organization_billing",
        ["organization_id"],
        unique=True,
    )
    _ensure_index(
        op.f("ix_organization_billing_subscription_tier"),
        "organization_billing",
        ["subscription_tier"],
        unique=False,
    )
    _ensure_index(
        op.f("ix_organization_billing_plan_code"),
        "organization_billing",
        ["plan_code"],
        unique=False,
    )


def _create_billing_invoices() -> None:
    op.create_table(
        "billing_invoices",
        sa.Column("id", sa.Uuid(native_uuid=True), nullable=False),
        sa.Column("public_id", sa.String(length=64), nullable=False),
        sa.Column("organization_id", sa.String(length=256), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("plan_code", sa.String(length=64), nullable=False),
        sa.Column("subscription_tier", sa.String(length=32), nullable=False),
        sa.Column("base_fee_cents", sa.Integer(), nullable=False),
        sa.Column("invoices_included", sa.Integer(), nullable=False),
        sa.Column("invoices_processed", sa.Integer(), nullable=False),
        sa.Column("overage_invoices", sa.Integer(), nullable=False),
        sa.Column("overage_rate_cents", sa.Integer(), nullable=False),
        sa.Column("overage_fee_cents", sa.Integer(), nullable=False),
        sa.Column("total_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def _ensure_billing_invoices_indexes() -> None:
    _ensure_index(
        op.f("ix_billing_invoices_public_id"), "billing_invoices", ["public_id"], unique=True
    )
    _ensure_index(
        op.f("ix_billing_invoices_organization_id"),
        "billing_invoices",
        ["organization_id"],
        unique=False,
    )
    _ensure_index(
        op.f("ix_billing_invoices_status"), "billing_invoices", ["status"], unique=False
    )
    _ensure_index(
        op.f("ux_billing_invoices_organization_id_period_start"),
        "billing_invoices",
        ["organization_id", "period_start"],
        unique=True,
    )
    _ensure_index(
        op.f("ix_billing_invoices_organization_id_period_start"),
        "billing_invoices",
        ["organization_id", "period_start"],
        unique=False,
    )


def downgrade() -> None:
    """Drops both tables and the unit column.

    Like `0009`'s, this destroys something commercial rather than something technical: every
    practice's plan assignment and every priced period exists nowhere else. Export both before
    running it against a real deployment — `organization_billing` in particular cannot be rebuilt
    from usage rows, because a plan assignment is an agreement rather than a derived figure.

    Present because `alembic downgrade base` then `upgrade head` is how the drift check in
    `tests/test_db_persistence.py` proves this file and `app/db/models.py` agree.

    Guarded object by object for the same reason `upgrade` is: the state this exists to unwind is
    often a partial one, and a downgrade that dies on an index that was never created leaves the
    database further from clean than it started.
    """
    _drop_index_if_exists(
        op.f("ix_billing_invoices_organization_id_period_start"), "billing_invoices"
    )
    _drop_index_if_exists(
        op.f("ux_billing_invoices_organization_id_period_start"), "billing_invoices"
    )
    _drop_index_if_exists(op.f("ix_billing_invoices_status"), "billing_invoices")
    _drop_index_if_exists(op.f("ix_billing_invoices_organization_id"), "billing_invoices")
    _drop_index_if_exists(op.f("ix_billing_invoices_public_id"), "billing_invoices")
    if _has_table("billing_invoices"):
        op.drop_table("billing_invoices")

    _drop_index_if_exists(op.f("ix_organization_billing_plan_code"), "organization_billing")
    _drop_index_if_exists(op.f("ix_organization_billing_subscription_tier"), "organization_billing")
    _drop_index_if_exists(op.f("ix_organization_billing_organization_id"), "organization_billing")
    if _has_table("organization_billing"):
        op.drop_table("organization_billing")

    if _has_column("api_usage_logs", "invoices_processed"):
        op.drop_column("api_usage_logs", "invoices_processed")
