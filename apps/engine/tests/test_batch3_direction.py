"""Which side of a batch-3 exclusion survives, checked against the sentence's own grammar.

`scripts/deterministic_rule_parser.py` states the hazard this file exists for, in its own words:

    A and D put the forbidden Ziffer first; B and E put it last. Getting that backwards is
    precisely the mistake the extractor can make and a reader can miss.

A reversed exclusion is the worst failure mode this rule set has, and the only one that is
invisible from every other angle. The row is well-formed. Its citation is verbatim. Its Ziffern
both exist. It fires, blocks exactly one position, prints a real paragraph of the GOÄ beside it —
and suppresses the wrong one. On the Abschnitt B provision below that is the difference between
dropping a €10 Beratung and dropping the €80 psychotherapy session the patient actually had.

So every generated row is re-derived here from its own `quote` by a parser that was written before
this batch, does not share a line of code with `scripts/build_batch3_rules.py`, and decides
direction structurally — from where `neben` sits relative to the verb — rather than from anything
the row asserts about itself.

**Scope, after F1.** This cross-check originally carried the finding it turned up on the *existing*
corpus — 35 hand-curated exclusions pointing the wrong way — as executable data, because a finding
that lives only in prose decays. That finding is closed: `docs/content/f1-exclusion-direction.md`
fixed the 35, and `tests/test_exclusion_direction.py` now makes the same assertion over all 948
exclusions the engine loads rather than over the hand-curated file alone. Those entries are gone
from here, as `docs/content/coverage-sprint-report-batch3.md` §6.1 said they would be; what remains
is the part that guards *this batch's generator*, which the corpus-wide test knows nothing about.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest

from app.config import RULES_DATA_DIR

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from deterministic_rule_parser import parse_provision, split_provisions  # noqa: E402

BATCH_INFIX = "_b3_"


def _manual_rows() -> list[dict]:
    path = RULES_DATA_DIR / "exclusions.manual.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _supported(row: dict) -> bool | None:
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


#: The three batch-3 provisions `parse_provision` returns `None` for, and why. Each is a limit of
#: that parser, not a doubt about the direction — all three are unambiguously "Neben <n> … sind
#: <d> nicht berechnungsfähig", so `<n>` is the blocker. Pinned by legal_basis with an exact row
#: count so a *fourth* unreadable provision, or one of these growing, fails instead of hiding.
UNREADABLE: dict[str, tuple[int, str]] = {
    "GOÄ Allgemeine Bestimmung zu Abschnitt M III 9": (
        9,
        "the official XML misspells the operative phrase as 'nicht errechnungsfähig', so "
        "`EXCLUSION_RE` does not match it at all. The quote keeps the defect (it is the source's "
        "sentence), and the form is plainly B: 'Neben den Leistungen nach den Nummer 3892 … sind "
        "die Leistungen nach den ummern 3572 … nicht errechnungsfähig'.",
    ),
    "GOÄ Anmerkung zu Nummer 435": (
        182,
        "form B with fourteen words between the verb and its object ('sind für die Dauer der "
        "stationären intensivmedizinischen Überwachung und Behandlung Leistungen nach …'), which "
        "`_B_SPLIT` ('ist|sind die Leistung') cannot bridge. The sentence opens with 'Neben der "
        "Leistung nach Nummer 435', so 435 is the blocker.",
    ),
}

#: The batch-3 provision the parser also cannot read, which needs no direction argument: the
#: Zuschlag groups are `mutual`, both sentences are printed in the GOÄ, and a mutual edge has no
#: side to get backwards. It names its positions by Buchstabe ("A bis D sowie K 1"), and
#: `expand_numbers` reads digits, so there is nothing there for it to expand either way.
MUTUAL_AND_LETTERED = "GOÄ Allgemeine Bestimmungen zu Abschnitt B V (Zuschläge A bis D, K 1)"


@pytest.fixture(scope="module")
def batch3_rows() -> list[dict]:
    rows = [r for r in _manual_rows() if BATCH_INFIX in r["rule_id"]]
    assert len(rows) > 400, f"only {len(rows)} batch-3 rows found — the sweep matched nothing"
    return rows


def test_every_readable_batch3_row_points_the_way_its_sentence_does(batch3_rows):
    wrong = [
        (r["rule_id"], r["from_ziffer"], r["to_ziffer"], r["legal_basis"])
        for r in batch3_rows
        if r["direction"] == "one_way" and _supported(r) is False
    ]
    assert wrong == [], (
        f"{len(wrong)} batch-3 exclusions run opposite to the sentence they quote — the blocked "
        f"Ziffer is being kept and the surviving one suppressed: {wrong[:5]}"
    )


def test_the_unreadable_provisions_are_exactly_the_three_we_know_about(batch3_rows):
    """A guard on the guard: the check above is vacuous for rows the parser skips."""
    unreadable: dict[str, int] = {}
    for row in batch3_rows:
        if row["direction"] == "one_way" and _supported(row) is None:
            unreadable[row["legal_basis"]] = unreadable.get(row["legal_basis"], 0) + 1

    expected = {basis: count for basis, (count, _) in UNREADABLE.items()}
    assert unreadable == expected, (
        "the set of batch-3 provisions the deterministic parser cannot read has changed. Each "
        "entry in UNREADABLE carries the reason its direction is safe anyway; a new one needs the "
        "same argument written down before it ships."
    )


def test_every_readable_provision_is_confirmed_row_by_row(batch3_rows):
    """Not a threshold — a partition.

    Every one-way provision in the batch is either wholly confirmed by the independent parser or
    wholly listed in `UNREADABLE` with a written argument. A provision that is half-confirmed
    would mean the parser read the sentence and disagreed about some of its pairs, which is a
    different and much worse thing than not being able to read it.
    """
    by_basis: dict[str, set[bool | None]] = {}
    for row in batch3_rows:
        if row["direction"] != "one_way":
            continue
        by_basis.setdefault(row["legal_basis"], set()).add(_supported(row))

    mixed = {basis: verdicts for basis, verdicts in by_basis.items() if len(verdicts) > 1}
    assert mixed == {}, f"provisions confirmed for some rows and not others: {mixed}"

    confirmed = sorted(b for b, v in by_basis.items() if v == {True})
    assert len(confirmed) >= 6, f"only {len(confirmed)} provisions independently confirmed"
