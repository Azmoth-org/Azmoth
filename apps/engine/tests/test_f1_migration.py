"""The F1 rename list, checked against the data it claims to describe — and run.

`alembic/versions/20260915_0014_f1_exclusion_direction.py` carries 35 `old -> new` rule
ids as a literal. A literal transcribed from a diff is exactly the kind of thing that is right on
the day it is written and wrong six months later, and the failure is silent: a rename that names
an id nothing has does nothing, and a review stays attached to a rule that no longer exists.

So the list is checked three ways — against the CSV it was derived from, for internal consistency,
and by actually running the migration against a database with a review in it.
"""

from __future__ import annotations

import csv
import importlib.util
from datetime import datetime, timezone
from pathlib import Path

import pytest
import sqlalchemy as sa

from app.config import RULES_DATA_DIR

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20260915_0014_f1_exclusion_direction.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("f1_migration", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def renames() -> tuple[tuple[str, str], ...]:
    return _load_migration().RENAMES


@pytest.fixture(scope="module")
def manual_rule_ids() -> set[str]:
    with (RULES_DATA_DIR / "exclusions.manual.csv").open(encoding="utf-8", newline="") as handle:
        return {row["rule_id"] for row in csv.DictReader(handle)}


def test_the_migration_renames_exactly_thirty_five_ids(renames):
    assert len(renames) == 35
    assert len({old for old, _ in renames}) == 35
    assert len({new for _, new in renames}) == 35


def test_every_new_id_is_a_rule_that_now_exists(renames, manual_rule_ids):
    """The half that catches a typo in the target column."""
    missing = sorted(new for _, new in renames if new not in manual_rule_ids)
    assert missing == [], f"migration renames reviews onto ids no rule has: {missing}"


def test_no_old_id_survived_the_fix(renames, manual_rule_ids):
    """The half that catches a rename the CSV did not actually make."""
    still_there = sorted(old for old, _ in renames if old in manual_rule_ids)
    assert still_there == [], (
        f"the migration renames reviews away from ids that still exist as rules: {still_there}"
    )


def test_no_new_id_collides_with_an_old_one(renames):
    """Why the migration can update row by row without ordering the statements.

    `rule_reviews.rule_id` is unique. If some id were both a rename source and a rename target,
    the order of the 35 updates would decide whether the middle of the migration hits a unique
    violation — a failure that would appear only with the right rows present.
    """
    overlap = {old for old, _ in renames} & {new for _, new in renames}
    assert overlap == set(), f"ids that are both a source and a target: {sorted(overlap)}"


def test_each_rename_is_the_same_edge_written_the_other_way(renames):
    """`excl_man_260_355` -> `excl_man_355_260`, not some unrelated rule."""
    wrong = []
    for old, new in renames:
        a = old.removeprefix("excl_man_")
        b = new.removeprefix("excl_man_")
        # The edge is the pair, so swapping it must give the other id back. Split on the *last*
        # underscore for the source and the first for the target, since Ziffern carry no
        # underscores but the pair separator is the only one either side.
        if sorted(a.rsplit("_", 1)) != sorted(b.split("_", 1)):
            wrong.append((old, new))
    assert wrong == [], f"renames that are not the same pair reversed: {wrong}"


async def test_the_migration_actually_moves_a_review(database, renames):
    """Run it. The list being right says nothing about the SQL being right.

    A review is planted under one of the old ids, the statement `upgrade()` issues is applied, and
    the row must come back under the new id — then `downgrade()`'s must put it back, because a
    data migration nobody can roll back is one nobody deploys on a Friday.

    The statement is taken from the migration module itself rather than retyped, so a test that
    passes is a test of the SQL that will actually run.
    """
    module = _load_migration()
    old, new = renames[0]

    async with database.session() as session:
        await session.execute(
            sa.text(
                "INSERT INTO rule_reviews "
                "(id, rule_id, status, reviewed_by, review_notes, created_at, updated_at) "
                "VALUES (:id, :rule_id, :status, :by, NULL, :now, :now)"
            ),
            {
                "id": "00000000-0000-0000-0000-0000000000f1",
                "rule_id": old,
                "status": "REJECTED",
                "by": "f1-migration-test",
                "now": datetime(2026, 9, 15, tzinfo=timezone.utc),
            },
        )

    async with database.session() as session:
        await session.execute(module._UPDATE, {"old": old, "new": new})
    async with database.session() as session:
        moved = await session.execute(
            sa.text("SELECT status FROM rule_reviews WHERE rule_id = :id"), {"id": new}
        )
        assert moved.scalar_one() == "REJECTED", "the review did not follow its rule to the new id"

    async with database.session() as session:
        await session.execute(module._UPDATE, {"old": new, "new": old})
    async with database.session() as session:
        back = await session.execute(
            sa.text("SELECT status FROM rule_reviews WHERE rule_id = :id"), {"id": old}
        )
        assert back.scalar_one() == "REJECTED", "downgrade did not put the review back"
