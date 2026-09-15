"""F1 — carry rule reviews across the 35 exclusion rule ids the direction fix renamed.

Revision ID: 0014_f1_exclusion_direction
Revises: 0013_patient_ziffer_history
Create Date: 2026-09-15

35 rows in `data/rules/exclusions.manual.csv` stored a GOÄ exclusion pointing the wrong way: in a
sentence of the form "Die Leistung nach Nummer 260 ist neben Leistungen nach den Nummern 355 bis
361 … nicht berechnungsfähig" the *subject* is the position that may not be charged, and those rows
recorded it as the position that survives. See `docs/content/f1-exclusion-direction.md` and
`apps/engine/tests/test_exclusion_direction.py`.

The correction swaps `from_ziffer` and `to_ziffer`. Every rule id in `data/rules/*.csv` encodes its
own edge — all 948 exclusion rows do, and `test_every_rule_id_still_encodes_its_own_edge` now
enforces it — so the ids move with the columns: `excl_man_260_355` becomes `excl_man_355_260`.

**`rule_reviews.rule_id` has no foreign key**, by design (`app/db/models.py`: "the thing it points
at is not in this database"). So nothing in the database stops a renamed id from orphaning a
review, and an orphaned review is not inert: `RuleStore.with_reviews` resolves by id, a review it
cannot find is silently not applied, and a rule a human had **REJECTED** would start enforcing
again. That is the one direction this migration exists to prevent.

In practice the table is expected to be empty of these ids — `GET /rules/review-queue` only offers
rules that are unverified in the CSV and all 35 are `verified: true`, so they never reach a
reviewer through the UI. `POST /rules/{rule_id}/review` accepts any id the store knows, though, so
"expected" is not "guaranteed", and a rename that is correct 99 % of the time and silently
un-rejects a rule the other 1 % is not a rename anyone should ship.

**What is deliberately *not* migrated.** A rule id also appears inside two JSON payload columns:
`proposals.solver_result_json` (the full `CodingResponse`, with a `rule_id` on every blocked
position and proof row) and `batch_files.report_json`. Those are write-once records of what the
engine said at the time, and `proposals.receipt_hash` was computed over that exact document —
`app/db/models.py` on the column: *"what has to be reproducible is the response as served."*
Rewriting an id there would not correct a past answer, it would falsify the record of one and
break its receipt. They are left alone on purpose.

That is the whole list. `rule_reviews.rule_id` is the only column in the schema that holds a rule
id as a live reference; `rule_proposals` keys on `ziffer`, and `proposals` carries
`rules_hash`/`rules_version`, not ids. `tests/test_f1_migration.py` pins the rename list against
the CSV so it cannot drift from the data it describes.

Reversible: `downgrade()` maps the ids back, so rolling back to 0013 alongside a revert of the CSV
leaves reviews attached to the rules they were written about.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_f1_exclusion_direction"
down_revision: str | None = "0013_patient_ziffer_history"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: old id -> new id, for the 35 rows the F1 fix corrected. Transcribed from the CSV diff, and
#: asserted against it by `tests/test_f1_migration.py` so this list cannot drift from the data.
RENAMES: tuple[tuple[str, str], ...] = (
    ("excl_man_A_B", "excl_man_B_A"),
    ("excl_man_A_C", "excl_man_C_A"),
    ("excl_man_A_D", "excl_man_D_A"),
    ("excl_man_E_F", "excl_man_F_E"),
    ("excl_man_E_G", "excl_man_G_E"),
    ("excl_man_E_H", "excl_man_H_E"),
    ("excl_man_F_45", "excl_man_45_F"),
    ("excl_man_F_46", "excl_man_46_F"),
    ("excl_man_F_48", "excl_man_48_F"),
    ("excl_man_F_52", "excl_man_52_F"),
    ("excl_man_G_45", "excl_man_45_G"),
    ("excl_man_G_46", "excl_man_46_G"),
    ("excl_man_G_48", "excl_man_48_G"),
    ("excl_man_G_52", "excl_man_52_G"),
    ("excl_man_H_45", "excl_man_45_H"),
    ("excl_man_H_46", "excl_man_46_H"),
    ("excl_man_H_48", "excl_man_48_H"),
    ("excl_man_H_52", "excl_man_52_H"),
    ("excl_man_48_1", "excl_man_1_48"),
    ("excl_man_48_50", "excl_man_50_48"),
    ("excl_man_48_51", "excl_man_51_48"),
    ("excl_man_48_52", "excl_man_52_48"),
    ("excl_man_260_355", "excl_man_355_260"),
    ("excl_man_260_356", "excl_man_356_260"),
    ("excl_man_260_357", "excl_man_357_260"),
    ("excl_man_260_360", "excl_man_360_260"),
    ("excl_man_260_361", "excl_man_361_260"),
    ("excl_man_260_626", "excl_man_626_260"),
    ("excl_man_260_627", "excl_man_627_260"),
    ("excl_man_260_628", "excl_man_628_260"),
    ("excl_man_260_629", "excl_man_629_260"),
    ("excl_man_260_630", "excl_man_630_260"),
    ("excl_man_260_631", "excl_man_631_260"),
    ("excl_man_260_632", "excl_man_632_260"),
    ("excl_man_260_648", "excl_man_648_260"),
)

_UPDATE = sa.text("UPDATE rule_reviews SET rule_id = :new WHERE rule_id = :old")


def _apply(pairs: Sequence[tuple[str, str]]) -> None:
    """One statement per id.

    `rule_reviews.rule_id` is `unique=True`, and a single `CASE` statement over all 35 would have
    to be ordered to avoid a transient collision on an id that is both a source and a target here
    (`excl_man_48_52` → `excl_man_52_48` while `excl_man_F_52` → `excl_man_52_F` …). Row by row,
    inside the migration's transaction, there is nothing to order: no new id collides with any old
    one, which `tests/test_f1_migration.py` asserts rather than leaving to the reader.
    """
    connection = op.get_bind()
    for old, new in pairs:
        connection.execute(_UPDATE, {"old": old, "new": new})


def upgrade() -> None:
    _apply(RENAMES)


def downgrade() -> None:
    _apply([(new, old) for old, new in RENAMES])
