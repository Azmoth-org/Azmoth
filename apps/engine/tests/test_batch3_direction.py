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

`test_the_known_inverted_batch1_rows_are_still_inverted` is not a batch-3 test. It is the finding
this cross-check turned up on the *existing* corpus, recorded as an executable xfail so it cannot
be lost: see `docs/content/coverage-sprint-report-batch3.md` §6.
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


# ==========================================================================================
# The finding on the existing corpus — see the module docstring and report §6
# ==========================================================================================

#: Rows from coverage-sprint **batch 1** whose sentence is form A but which were entered as if it
#: were form B. In each one the *subject* of the sentence is the position that may not be charged,
#: and it was recorded as the one that survives. The auto-extractor gets the identical shape right
#: — `excl_auto_626_355`, from "Die Leistung nach Nummer 355 ist neben … 626 … nicht
#: berechnungsfähig", stores 626 → 355 — so the corpus currently disagrees with itself about which
#: way this shape points.
#:
#: Split by **what proves it**, because the two halves are not equally proven and saying otherwise
#: would be the same kind of overclaim this whole module is about.
#:
#: Not fixed here. Flipping an enforced exclusion changes which position a real invoice loses, and
#: that belongs in a change a reviewer can see on its own, not inside a 505-row data commit. See
#: `docs/content/coverage-sprint-report-batch3.md` §6.

#: Machine-confirmed: `parse_provision` reads these quotes and returns the opposite edge.
#:
#: The four GOÄ 48 rows are the worse half. A *reverse* auto-extracted rule exists for each
#: (`excl_auto_1_48`, `excl_auto_50_48`, …) and is correct, but LAYER 3 of
#: `logic/datalog/goae_rules.dl` only decides a one-way edge when the opposite edge is absent
#: (`!exclusion(_, B, A, _)`). So the inverted row does not merely point the wrong way — it
#: silences the correct rule, and GOÄ 48 beside GOÄ 50 is caught by nothing at all today.
INVERTED_CONFIRMED_BY_PARSER = (
    "excl_man_260_355", "excl_man_260_356", "excl_man_260_357", "excl_man_260_360",
    "excl_man_260_361", "excl_man_260_626", "excl_man_260_627", "excl_man_260_628",
    "excl_man_260_629", "excl_man_260_630", "excl_man_260_631", "excl_man_260_632",
    "excl_man_260_648",
    "excl_man_48_1", "excl_man_48_50", "excl_man_48_51", "excl_man_48_52",
)

#: Read by hand, and *not* machine-confirmable: the blocked side of each sentence is named by
#: Buchstabe ("Der Zuschlag nach Buchstabe F ist neben den Leistungen nach den Nummern 45, 46, 48
#: und 52 nicht berechnungsfähig"), and `expand_numbers` reads digits, so the parser returns no
#: verdict rather than the wrong one. The grammar is the same form A as the rows above — the
#: Zuschlag is the sentence's subject and is therefore the position that may not be charged — but
#: the evidence here is a person reading German, so these are listed separately and pinned only by
#: the edge they currently assert.
INVERTED_READ_BY_HAND = {
    "excl_man_A_B": ("A", "B"), "excl_man_A_C": ("A", "C"), "excl_man_A_D": ("A", "D"),
    "excl_man_E_F": ("E", "F"), "excl_man_E_G": ("E", "G"), "excl_man_E_H": ("E", "H"),
    "excl_man_F_45": ("F", "45"), "excl_man_F_46": ("F", "46"),
    "excl_man_F_48": ("F", "48"), "excl_man_F_52": ("F", "52"),
    "excl_man_G_45": ("G", "45"), "excl_man_G_46": ("G", "46"),
    "excl_man_G_48": ("G", "48"), "excl_man_G_52": ("G", "52"),
    "excl_man_H_45": ("H", "45"), "excl_man_H_46": ("H", "46"),
    "excl_man_H_48": ("H", "48"), "excl_man_H_52": ("H", "52"),
}


def test_the_machine_confirmed_half_of_the_finding_still_describes_the_corpus():
    """The 17 rows the parser can read are still pointing the way the finding says.

    A plain assertion rather than an `xfail` on the direction check, so that *fixing* them fails
    loudly with the report section to update named in the message — an xfail would flip to XPASS
    and be easy to scroll past.
    """
    by_id = {r["rule_id"]: r for r in _manual_rows()}
    missing = [rid for rid in INVERTED_CONFIRMED_BY_PARSER if rid not in by_id]
    assert missing == [], f"finding §6 names rules that no longer exist: {missing}"

    fixed = sorted(
        rid for rid in INVERTED_CONFIRMED_BY_PARSER if _supported(by_id[rid]) is not False
    )
    assert not fixed, (
        f"{len(fixed)} of the rules recorded as inverted in "
        f"docs/content/coverage-sprint-report-batch3.md §6 no longer are: {fixed}. If they were "
        f"fixed on purpose, drop them from INVERTED_CONFIRMED_BY_PARSER and close out §6 — the "
        f"finding and the corpus must not disagree."
    )


def test_the_hand_read_half_of_the_finding_still_describes_the_corpus():
    by_id = {r["rule_id"]: r for r in _manual_rows()}
    actual = {
        rid: (by_id[rid]["from_ziffer"], by_id[rid]["to_ziffer"])
        for rid in INVERTED_READ_BY_HAND
        if rid in by_id
    }
    assert actual == INVERTED_READ_BY_HAND, (
        "the Zuschlag rows recorded as inverted in §6 have moved. If they were corrected, update "
        "INVERTED_READ_BY_HAND and close out §6."
    )


def test_no_other_manual_rule_is_inverted():
    """The finding claims to be complete, for everything the parser can decide. This is what
    makes that claim falsifiable — and it is why `INVERTED_READ_BY_HAND` is scoped by the parser
    being silent rather than by anybody's confidence."""
    known = set(INVERTED_CONFIRMED_BY_PARSER) | set(INVERTED_READ_BY_HAND)
    newly = [
        r["rule_id"]
        for r in _manual_rows()
        if r["rule_id"].startswith("excl_man_")
        and r["direction"] == "one_way"
        and r["rule_id"] not in known
        and _supported(r) is False
    ]
    assert newly == [], f"inverted hand-curated exclusions the finding does not list: {newly}"
