"""Which side of every exclusion survives, checked against the sentence it quotes.

`scripts/deterministic_rule_parser.py` names the hazard in its own docstring:

    A and D put the forbidden Ziffer first; B and E put it last. Getting that backwards is
    precisely the mistake the extractor can make and a reader can miss.

A reversed exclusion is the worst failure this rule set has and the only one invisible from every
other angle. The row is well-formed. Its citation is verbatim. Both Ziffern exist. It fires, blocks
exactly one position, prints a real paragraph of the GOÄ beside it — **and suppresses the wrong
one.** Nothing in the schema, the CSV linting, the citation checks or the golden corpus can see it,
because every one of those is satisfied by a rule pointing either way.

That is not hypothetical: 35 hand-curated rules shipped inverted, and this module is the fix's
regression guard. It checks **every** exclusion the engine loads, not the 35, because the 35 were
only ever a symptom — the defect was that nothing compared a stored edge against its own sentence.

Two levels:

  * **every row** — re-derive the edge from the row's own `quote` with a parser that shares no
    code with whatever produced the row, and compare. Rows that parser cannot read are enumerated
    below, by quote, with the reading that justifies them, so the check cannot be hollowed out by
    a sentence shape the parser happens to choke on.
  * **the engine** — claim the pairs on a real invoice and assert the correct side is the one that
    disappears. A CSV can be right while the Datalog layer does nothing with it: four of the 35
    had a correct auto-extracted twin, and LAYER 3 only decides a one-way edge when the opposite
    edge is absent (`!exclusion(_, B, A, _)`), so the inverted row *silenced* the correct one and
    GOÄ 48 beside GOÄ 50 was caught by nothing at all.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest

from app.config import RULES_DATA_DIR
from tests.conftest import make_extraction, one_act_per_ziffer

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from deterministic_rule_parser import parse_provision, split_provisions  # noqa: E402

#: Every file `RuleStore.load` reads exclusions from. `exclusions.residue.csv` is deliberately
#: absent: those rows are `NEEDS_HUMAN_REVIEW`, never admitted by any policy, and their direction
#: is not a claim the engine makes.
EXCLUSION_FILES = ("exclusions.csv", "exclusions.manual.csv")


def _rows() -> list[tuple[str, dict]]:
    out: list[tuple[str, dict]] = []
    for name in EXCLUSION_FILES:
        path = RULES_DATA_DIR / name
        if not path.exists():
            continue
        with path.open(encoding="utf-8", newline="") as handle:
            out += [(name, row) for row in csv.DictReader(handle)]
    return out


def _verdict(row: dict) -> bool | None:
    """True/False if the row's own quote decides the edge, None if the parser cannot read it."""
    readable = False
    for sentence in split_provisions(row["quote"]):
        provision = parse_provision(sentence)
        if provision is None:
            continue
        readable = True
        if provision.supports(row["from_ziffer"], row["to_ziffer"]):
            return True
    return False if readable else None


# ==============================================================================================
# The sentences `parse_provision` returns None for, and the reading that stands in for it.
# ==============================================================================================

#: Keyed by a verbatim fragment of the quote; the value is why the stored direction is right.
#: Every one of these was read by a person, and the reading is written down so a reviewer can
#: disagree with it — which is the whole difference between "the parser cannot check this" and
#: "this is unchecked".
#:
#: All eleven are *form B or E* — the sentence opens with "Neben"/"Anstelle oder neben", so the
#: Ziffer named first is the one whose presence forbids the others. None is form A, which is the
#: shape all 35 inverted rows were.
HAND_READ: dict[str, str] = {
    "Neben der Leistung nach Nummer 1473 ist die Nummer 1485 nicht berechnungsfähig": (
        "form B. `_B_SPLIT` looks for 'ist die Leistung'; this sentence writes 'ist die Nummer'. "
        "1473 is named after 'Neben', so 1473 is the blocker."
    ),
    "Anstelle oder neben der Visite im Krankenhaus sind die Leistungen nach den Nummern": (
        "form B with the blocker named by its Leistungslegende rather than its number — 'die "
        "Visite im Krankenhaus' is GOÄ 45's legend, word for word — so the parser finds no number "
        "on that side. 45 is the blocker."
    ),
    "Anstelle oder neben der Zweitvisite im Krankenhaus sind die Leistungen nach den Nummern": (
        "the same shape for GOÄ 46, whose legend is 'Zweitvisite im Krankenhaus'."
    ),
    "Neben oder anstelle der computergesteuerten Tomographie zur Bestrahlungsplanung": (
        "form B, blocker named descriptively ('der computergesteuerten Tomographie zur "
        "Bestrahlungsplanung' — GOÄ 5378's legend), so no number appears before the verb."
    ),
    "Neben dem Zuschlag nach Buchstabe C ist der Zuschlag nach Buchstabe B nicht": (
        "form B. Both sides are Buchstaben and `expand_numbers` reads digits, so the parser sees "
        "nothing at all. C is named after 'Neben' and is the blocker."
    ),
    "Neben dem Zuschlag nach Buchstabe G ist der Zuschlag nach Buchstabe F nicht": (
        "form B, both sides Buchstaben. G is the blocker."
    ),
    #: The five form-A sentences the fix corrected. They stay unreadable — their *blocked* side is
    #: a Buchstabe — which is exactly why they went unnoticed, and why they are spelled out here.
    "Der Zuschlag nach Buchstabe A ist neben den Zuschlägen nach den Buchstaben B, C und/oder D": (
        "form A: the Zuschlag nach Buchstabe A is the subject and is therefore the position that "
        "may not be charged. B, C, D are the blockers. Corrected by the F1 fix."
    ),
    "Der Zuschlag nach Buchstabe E ist neben Zuschlägen nach den Buchstaben F, G und/oder H": (
        "form A: E is blocked, F/G/H block. Corrected by the F1 fix."
    ),
    "Der Zuschlag nach Buchstabe F ist neben den Leistungen nach den Nummern 45, 46, 48 und 52": (
        "form A: F is blocked, 45/46/48/52 block. Corrected by the F1 fix."
    ),
    "Der Zuschlag nach Buchstabe G ist neben den Leistungen nach den Nummern 45, 46, 48 und 52": (
        "form A: G is blocked, 45/46/48/52 block. Corrected by the F1 fix."
    ),
    "Der Zuschlag nach Buchstabe H ist neben den Leistungen nach den Nummern 45, 46, 48 und 52": (
        "form A: H is blocked, 45/46/48/52 block. Corrected by the F1 fix."
    ),
}


@pytest.fixture(scope="module")
def rows() -> list[tuple[str, dict]]:
    loaded = _rows()
    assert len(loaded) > 900, f"only {len(loaded)} exclusion rows found — the sweep matched nothing"
    return loaded


# ==============================================================================================
# every row
# ==============================================================================================


def test_no_exclusion_runs_opposite_to_the_sentence_it_quotes(rows):
    """The check that would have caught F1 the day it was written."""
    wrong = [
        (name, row["rule_id"], f"{row['from_ziffer']}->{row['to_ziffer']}", row["quote"][:70])
        for name, row in rows
        if row["direction"] == "one_way" and _verdict(row) is False
    ]
    assert wrong == [], (
        f"{len(wrong)} exclusions keep the Ziffer their sentence forbids and suppress the one it "
        f"protects: {wrong[:5]}"
    )


def test_every_unreadable_sentence_has_a_written_reading(rows):
    """A guard on the guard: the check above is vacuous for rows the parser skips.

    Without this, a future batch could add a sentence shape `parse_provision` cannot read and the
    sweep above would pass by saying nothing about it.
    """
    unexplained = sorted(
        {
            (row["rule_id"], row["quote"][:95])
            for _, row in rows
            if row["direction"] == "one_way"
            and _verdict(row) is None
            and not any(fragment in row["quote"] for fragment in HAND_READ)
        }
    )
    assert unexplained == [], (
        "exclusion rows whose direction neither the parser nor HAND_READ decides. Add the "
        f"sentence to HAND_READ with the reading that justifies it: {unexplained[:3]}"
    )


def test_the_cross_check_actually_covers_the_corpus(rows):
    """Most of the corpus must be machine-confirmed, or this file is a comment."""
    one_way = [row for _, row in rows if row["direction"] == "one_way"]
    confirmed = sum(1 for row in one_way if _verdict(row) is True)
    assert confirmed >= 0.9 * len(one_way), (
        f"only {confirmed} of {len(one_way)} one-way exclusions were machine-confirmed; the rest "
        f"rest on HAND_READ, which is a reader's word rather than a check"
    )


def test_every_hand_read_entry_still_matches_a_row(rows):
    """An entry that matches nothing is a licence nobody is using — and one somebody could."""
    quotes = [row["quote"] for _, row in rows]
    unused = [f for f in HAND_READ if not any(f in q for q in quotes)]
    assert unused == [], f"HAND_READ entries matching no rule: {unused}"


def test_every_rule_id_still_encodes_its_own_edge(rows):
    """`excl_man_260_355` must mean 260 → 355.

    Not cosmetic. The id is the only place the direction is visible without opening the CSV and
    reading German, so an id that disagrees with its columns is how a corrected rule gets
    "corrected" back. All 948 rows followed this convention before the F1 fix and all of them
    follow it after, which is what let the fix be a pure rename plus a column swap.
    """
    mismatched = [
        (name, row["rule_id"], f"{row['from_ziffer']}->{row['to_ziffer']}")
        for name, row in rows
        if not row["rule_id"].endswith(f"_{row['from_ziffer']}_{row['to_ziffer']}")
    ]
    assert mismatched == [], f"rule ids that do not encode their own edge: {mismatched[:5]}"


# ==============================================================================================
# the engine
# ==============================================================================================

#: `(charged together, the one that must disappear, the rule that must say so)` — one per
#: sentence the F1 fix corrected, plus the two shapes it did not touch, so a future edit that
#: "fixes" a correct rule fails here too.
DIRECTED_PAIRS = (
    ("B", "A", "excl_man_B_A"),
    ("C", "A", "excl_man_C_A"),
    ("D", "A", "excl_man_D_A"),
    ("F", "E", "excl_man_F_E"),
    ("G", "E", "excl_man_G_E"),
    ("H", "E", "excl_man_H_E"),
    ("45", "F", "excl_man_45_F"),
    ("52", "F", "excl_man_52_F"),
    ("45", "G", "excl_man_45_G"),
    ("52", "H", "excl_man_52_H"),
    ("355", "260", "excl_man_355_260"),
    ("626", "260", "excl_man_626_260"),
    ("648", "260", "excl_man_648_260"),
    ("1", "48", "excl_man_1_48"),
    ("50", "48", "excl_man_50_48"),
    ("51", "48", "excl_man_51_48"),
    ("52", "48", "excl_man_52_48"),
    # Untouched by F1, and here so that "fixing" them is also caught.
    ("C", "B", "excl_man_C_B"),
    ("G", "F", "excl_man_G_F"),
    ("45", "1", "excl_man_45_1"),
    ("1473", "1485", "excl_man_1473_1485"),
)


@pytest.mark.parametrize("survivor,blocked,rule_id", DIRECTED_PAIRS)
def test_the_engine_suppresses_the_side_the_sentence_forbids(souffle, survivor, blocked, rule_id):
    result = souffle.run(make_extraction(), one_act_per_ziffer(survivor, blocked))

    assert result.billable == [survivor], (
        f"GOÄ {survivor} + {blocked}: expected {survivor} to survive, got {result.billable}"
    )
    finding = next((b for b in result.blocked if b.ziffer == blocked), None)
    assert finding is not None, f"GOÄ {blocked} was not blocked beside {survivor}"
    assert finding.rule_id == rule_id, f"blocked by {finding.rule_id}, expected {rule_id}"


@pytest.mark.parametrize("a,b", [("48", "50"), ("48", "1"), ("48", "51"), ("48", "52")])
def test_the_pairs_a_reversed_rule_had_silenced_are_caught_again(souffle, a, b):
    """The second harm, which is worse than pointing the wrong way.

    Each of these had a correct auto-extracted rule (`excl_auto_50_48`, …) *and* an inverted
    hand-curated one. LAYER 3 decides a one-way edge only when the opposite edge is absent, so
    with both present neither fired and the combination was caught by nothing at all — a verified
    rule enforcing nothing, which no coverage figure in this repo could show.
    """
    result = souffle.run(make_extraction(), one_act_per_ziffer(a, b))

    assert result.blocked, f"GOÄ {a} + {b} produced no finding at all"
    assert [x.ziffer for x in result.blocked] == ["48"], (
        f"GOÄ 48 is the position its Anmerkung forbids beside {b}; blocked {result.blocked}"
    )
