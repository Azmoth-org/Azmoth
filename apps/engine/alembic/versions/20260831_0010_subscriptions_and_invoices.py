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


def upgrade() -> None:
    # ------------------------------------------------------------------------------------------
    # 1. the billable unit
    # ------------------------------------------------------------------------------------------
    # `server_default="0"` and not merely a Python-side default: this is an ALTER on a table that
    # may already hold rows, and Postgres needs a value for them. The server default is dropped
    # immediately afterwards so the column matches `app/db/models.py`, where the default is
    # application-side — the same discipline `utcnow` follows, and what keeps the drift check in
    # `tests/test_db_persistence.py` honest.
    op.add_column(
        "api_usage_logs",
        sa.Column("invoices_processed", sa.Integer(), nullable=False, server_default="0"),
    )
    with op.batch_alter_table("api_usage_logs") as batch:
        batch.alter_column("invoices_processed", server_default=None)

    # ------------------------------------------------------------------------------------------
    # 2. the entitlement
    # ------------------------------------------------------------------------------------------
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
    op.create_index(
        op.f("ix_organization_billing_organization_id"),
        "organization_billing",
        ["organization_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_organization_billing_subscription_tier"),
        "organization_billing",
        ["subscription_tier"],
        unique=False,
    )
    op.create_index(
        op.f("ix_organization_billing_plan_code"),
        "organization_billing",
        ["plan_code"],
        unique=False,
    )

    # ------------------------------------------------------------------------------------------
    # 3. what a closed period came to
    # ------------------------------------------------------------------------------------------
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
    op.create_index(
        op.f("ix_billing_invoices_public_id"), "billing_invoices", ["public_id"], unique=True
    )
    op.create_index(
        op.f("ix_billing_invoices_organization_id"),
        "billing_invoices",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_billing_invoices_status"), "billing_invoices", ["status"], unique=False
    )
    op.create_index(
        op.f("ux_billing_invoices_organization_id_period_start"),
        "billing_invoices",
        ["organization_id", "period_start"],
        unique=True,
    )
    op.create_index(
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
    """
    op.drop_index(
        op.f("ix_billing_invoices_organization_id_period_start"), table_name="billing_invoices"
    )
    op.drop_index(
        op.f("ux_billing_invoices_organization_id_period_start"), table_name="billing_invoices"
    )
    op.drop_index(op.f("ix_billing_invoices_status"), table_name="billing_invoices")
    op.drop_index(op.f("ix_billing_invoices_organization_id"), table_name="billing_invoices")
    op.drop_index(op.f("ix_billing_invoices_public_id"), table_name="billing_invoices")
    op.drop_table("billing_invoices")

    op.drop_index(op.f("ix_organization_billing_plan_code"), table_name="organization_billing")
    op.drop_index(
        op.f("ix_organization_billing_subscription_tier"), table_name="organization_billing"
    )
    op.drop_index(
        op.f("ix_organization_billing_organization_id"), table_name="organization_billing"
    )
    op.drop_table("organization_billing")

    op.drop_column("api_usage_logs", "invoices_processed")
