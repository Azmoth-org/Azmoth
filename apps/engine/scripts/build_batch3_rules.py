#!/usr/bin/env python3
"""Generate the coverage-sprint **batch 3** rule rows, deterministically.

    python scripts/build_batch3_rules.py              # rewrite the batch-3 rows in place
    python scripts/build_batch3_rules.py --check      # exit 1 if any file would change
    python scripts/build_batch3_rules.py --report     # coverage delta, no writes

Batch 1 and batch 2 were hand-entered. Batch 3 cannot be: a single provision here
(the Anmerkung to GOÄ 435) states 182 exclusion edges, and three more state 30 apiece. Typing
560-odd CSV rows by hand is not more trustworthy than generating them — it is less, because a
transcription slip in row 400 looks exactly like the other 399.

So this script is the source of truth for batch 3's rows, and `PROVISIONS` below is the only
place a human judgement was made. Each entry names:

  * the **exact sentence** it encodes, copied verbatim out of
    `data/catalogs/goae_current/allgemeine_bestimmungen.json` or out of a Ziffer's `annotations`
    in `goae.official.json` — asserted present in one of those two, byte for byte, on every run
    (`--check` in CI, and `tests/test_batch3_citations.py`);
  * the **Ziffer tokens** that sentence names, transcribed in the order the sentence writes them,
    `("804", "bis", "812")` for "804 bis 812". Expansion is mechanical from there, so the only
    thing a reviewer has to check is that the token list matches the quote.

Rows are rewritten in place: every row whose `rule_id` carries the batch-3 infix is dropped and
regenerated, so re-running produces a byte-identical file and a changed `PROVISIONS` entry shows
up as a normal diff instead of an append-only pile-up.

**What is deliberately not here** is written up in `docs/content/coverage-sprint-report-batch3
.md` §4 and pinned as data in `tests/test_batch3_quarantine.py`. The short version: a provision
whose scope is an *Abschnitt* rather than a list of numbers (GOÄ 437's "Leistungen nach
Abschnitt M"), one conditioned on a fact an invoice does not carry ("an demselben Gelenk", "durch
einen Belegarzt"), and one whose window this engine cannot evaluate ("je Sitzung") are all left
alone, exactly as batch 1 and batch 2 left their equivalents alone.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[1]


def _find_repo_root() -> Path:
    for candidate in (ENGINE_ROOT, *ENGINE_ROOT.parents):
        if (candidate / "logic").is_dir() and (candidate / "data").is_dir():
            return candidate
    return ENGINE_ROOT.parent.parent


REPO_ROOT = _find_repo_root()
RULES_DIR = REPO_ROOT / "data" / "rules"
CATALOG = REPO_ROOT / "data" / "catalogs" / "goae_current" / "goae.official.json"
PROVISIONS_JSON = REPO_ROOT / "data" / "catalogs" / "goae_current" / "allgemeine_bestimmungen.json"

EXCLUSIONS_FILE = RULES_DIR / "exclusions.manual.csv"
FACTOR_CAPS_FILE = RULES_DIR / "factor_caps.csv"

#: Stamped on every generated row. `BATCH` is also the infix that makes a row identifiable for
#: regeneration — `excl_b3_…`, `cap_b3_…` — so it must not appear in any hand-entered rule_id.
BATCH = "b3"
VERIFIED_AT = "2026-09-15"
SOURCE = "manual_verification:coverage_sprint_batch3"

# ==================================================================================================
# The judgement calls. Everything below this block is mechanical.
# ==================================================================================================


@dataclass(frozen=True)
class Provision:
    """One GOÄ sentence and the rule rows it states.

    `kind` is one of:

      ``one_way``   a directed exclusion. **Which side survives is decided by `form`, not by the
                    order of the two lists** — see `form` below.
      ``mutual``    every Ziffer in `left` and every Ziffer in `right` exclude each other, both
                    directions written as rows (`RuleStore` reads a mutual pair as two rows — see
                    `excl_man_5_6` / `excl_man_6_5`). When `right` is empty, `left` is a clique:
                    "Die Leistungen nach den Nummern 271 bis 276 sind nicht nebeneinander …"
      ``factor_cap`` every Ziffer in `left` is capped at `max_factor`.
    """

    key: str
    kind: str
    legal_basis: str
    quote: str
    #: The two Ziffer groups **in the order the sentence writes them**, so a reviewer checks the
    #: token lists against the quote left to right and never has to reason about direction here.
    left: tuple[str, ...]
    right: tuple[str, ...] = ()
    #: Which German sentence shape the quote is, from the five `scripts/deterministic_rule_parser
    #: .py` enumerates. It is the *only* thing that decides which side of a `one_way` exclusion
    #: survives, and that file says why it is worth a field of its own:
    #:
    #:     A and D put the forbidden Ziffer first; B and E put it last. Getting that backwards is
    #:     precisely the mistake the extractor can make and a reader can miss.
    #:
    #:   ``B``  "**Neben** den Leistungen nach <n> **sind** die Leistungen nach <d> nicht
    #:          berechnungsfähig."  → `left` survives, `right` is blocked.
    #:   ``A``  "Die Leistungen nach <d> **sind neben** den Leistungen nach <n> nicht
    #:          berechnungsfähig."  → `left` is blocked, `right` survives. The subject of the
    #:          sentence is the position that may not be charged.
    #:
    #: Ignored for ``mutual`` and ``factor_cap``, where there is no direction to get wrong.
    form: str = "B"
    #: For a ``mutual`` provision stated by *two* sentences — one in each section's Allgemeine
    #: Bestimmungen, with the groups swapped — the sentence that states the `right` → `left`
    #: direction. Rows in that direction then cite the sentence that actually says so, instead of
    #: the mirror image of it in the neighbouring provision. Optional; without it both directions
    #: cite `quote`.
    reverse_quote: str = ""
    reverse_legal_basis: str = ""
    reverse_cite_in: str = ""
    max_factor: str = ""
    #: Where `quote` must be found verbatim: a provision id in `allgemeine_bestimmungen.json`
    #: (``ab_17``) or a Ziffer whose catalog `annotations` carry it (``ziffer:435``).
    cite_in: str = ""
    note: str = ""


PROVISIONS: tuple[Provision, ...] = (
    # ── Abschnitt B — Grundleistungen und allgemeine Leistungen ────────────────────────────────
    Provision(
        key="b_beratung_psych",
        kind="one_way",
        cite_in="ab_01",
        legal_basis="GOÄ Allgemeine Bestimmungen zu Abschnitt B, Nr. 4",
        quote=(
            "Die Leistungen nach den Nummern 1, 3, 22, 30 und/oder 34 sind neben den Leistungen "
            "nach den Nummern 804 bis 812, 817, 835, 849, 861 bis 864, 870, 871, 886 sowie 887 "
            "nicht berechnungsfähig."
        ),
        form="A",
        left=("1", "3", "22", "30", "34"),
        right=(
            "804", "bis", "812", "817", "835", "849", "861", "bis", "864", "870", "871", "886",
            "887",
        ),
        note=(
            "Form A: the Beratung/Erörterung positions are the sentence's subject, so *they* are "
            "the ones that may not be charged, and the psychiatric/psychotherapeutic session is "
            "what survives. Encoding it the other way round would suppress the therapy session — "
            "the higher-valued position, and the one the patient actually received."
        ),
    ),
    Provision(
        key="b_untersuchung_teilleistungen",
        kind="one_way",
        cite_in="ab_01",
        legal_basis="GOÄ Allgemeine Bestimmungen zu Abschnitt B, Nr. 8",
        quote=(
            "Neben einer Leistung nach Nummer 5, 6, 7 oder 8 sind die Leistungen nach den Nummern "
            "600, 601, 1203, 1204, 1228, 1240, 1400, 1401 und 1414 nicht berechnungsfähig."
        ),
        left=("5", "6", "7", "8"),
        right=("600", "601", "1203", "1204", "1228", "1240", "1400", "1401", "1414"),
        note="Organ-specific sub-examinations already contained in the general examination.",
    ),
    Provision(
        key="b_zuschlag_gruppen",
        kind="mutual",
        cite_in="ab_02",
        legal_basis="GOÄ Allgemeine Bestimmungen zu Abschnitt B V (Zuschläge A bis D, K 1)",
        quote=(
            "Neben den Zuschlägen nach den Buchstaben A bis D sowie K 1 dürfen die Zuschläge nach "
            "den Buchstaben E bis J sowie K 2 nicht berechnet werden."
        ),
        left=("A", "B", "C", "D", "K1"),
        right=("E", "F", "G", "H", "J", "K2"),
        reverse_cite_in="ab_03",
        reverse_legal_basis=(
            "GOÄ Allgemeine Bestimmungen zu Abschnitt B V (Zuschläge E bis J, K 2)"
        ),
        reverse_quote=(
            "Neben den Zuschlägen nach den Buchstaben E bis J sowie K 2 dürfen die Zuschläge "
            "nach den Buchstaben A bis D sowie K 1 nicht berechnet werden."
        ),
        note=(
            "Mutual because the GOÄ prints the sentence twice with the groups swapped, once in "
            "each group's own Allgemeine Bestimmungen. Each direction's rows cite the sentence "
            "that states that direction, rather than both citing one and leaving a reader to "
            "notice the mirror image is what actually covers half of them."
        ),
    ),
    Provision(
        key="b_zuschlag_ad_k1_cap",
        kind="factor_cap",
        cite_in="ab_02",
        legal_basis="GOÄ Allgemeine Bestimmungen zu Abschnitt B V (Zuschläge A bis D, K 1)",
        quote=(
            "Die Zuschläge nach den Buchstaben A bis D sowie K 1 sind nur mit dem einfachen "
            "Gebührensatz berechnungsfähig."
        ),
        left=("A", "B", "C", "D", "K1"),
        max_factor="1.0",
    ),
    Provision(
        key="b_zuschlag_ej_k2_cap",
        kind="factor_cap",
        cite_in="ab_03",
        legal_basis="GOÄ Allgemeine Bestimmungen zu Abschnitt B V (Zuschläge E bis J, K 2)",
        quote=(
            "Die Zuschläge nach den Buchstaben E bis J sowie K 2 sind nur mit dem einfachen "
            "Gebührensatz berechnungsfähig."
        ),
        left=("E", "F", "G", "H", "J", "K2"),
        max_factor="1.0",
        note=(
            "The next sentence lowers the ceiling to half beside GOÄ 51 ('Abweichend hiervon sind "
            "die Zuschläge nach den Buchstaben E bis H neben der Leistung nach Nummer 51 nur mit "
            "dem halben Gebührensatz berechnungsfähig'). A cap of 1.0 is the unconditional "
            "sentence; it under-blocks that one combination rather than over-blocking anything, "
            "the same direction batch 1 took on GOÄ 95/96."
        ),
    ),
    # ── Abschnitt B VII — Todesfeststellung ────────────────────────────────────────────────────
    Provision(
        key="b_leichenschau_besuch",
        kind="one_way",
        cite_in="ab_04",
        legal_basis="GOÄ Allgemeine Bestimmungen zu Abschnitt B VII, Nr. 3",
        quote=(
            "Neben den Leistungen nach den Nummern 100 und 101 sind die Leistungen nach den "
            "Nummern 48 bis 52 nicht berechnungsfähig."
        ),
        left=("100", "101"),
        right=("48", "bis", "52"),
    ),
    Provision(
        key="b_leichenschau_mutual",
        kind="mutual",
        cite_in="ab_04",
        legal_basis="GOÄ Allgemeine Bestimmungen zu Abschnitt B VII, Nr. 4",
        quote="Die Leistungen nach den Nummern 100 und 101 sind nicht nebeneinander berechnungsfähig.",
        left=("100", "101"),
    ),
    Provision(
        key="b_leichenschau_cap",
        kind="factor_cap",
        cite_in="ab_04",
        legal_basis="GOÄ Allgemeine Bestimmungen zu Abschnitt B VII, Nr. 5",
        quote=(
            "Die Leistungen nach den Nummern 100 und 101 sowie der Zuschlag nach Nummer 102 sind "
            "nur mit dem einfachen Gebührensatz berechnungsfähig."
        ),
        left=("100", "101", "102"),
        max_factor="1.0",
    ),
    # ── Abschnitt C II — Injektionen, Infusionen ───────────────────────────────────────────────
    Provision(
        key="c_infusionen_mutual",
        kind="mutual",
        cite_in="ab_06",
        legal_basis="GOÄ Allgemeine Bestimmungen zu Abschnitt C II",
        quote="Die Leistungen nach den Nummern 271 bis 276 sind nicht nebeneinander berechnungsfähig.",
        left=("271", "bis", "276"),
    ),
    # ── Abschnitt C V — Impfungen und Testungen ────────────────────────────────────────────────
    Provision(
        key="c_impfung_beratung",
        kind="one_way",
        cite_in="ab_09",
        legal_basis="GOÄ Allgemeine Bestimmungen zu Abschnitt C V",
        quote=(
            "Neben den Leistungen nach den Nummern 376 bis 378 sind die Leistungen nach den "
            "Nummern 1 und 2 und die gegebenenfalls erforderliche Eintragung in den Impfpaß nicht "
            "berechnungsfähig."
        ),
        left=("376", "bis", "378"),
        right=("1", "2"),
        note=(
            "The third limb — 'die gegebenenfalls erforderliche Eintragung in den Impfpaß' — names "
            "an act, not a Ziffer, and is not encoded. GOÄ 375 is deliberately outside the range: "
            "the sentence says 376, and 375's own Leistungslegende already contains the Beratung "
            "('einschließlich beratendem Gespräch'), which is a different mechanism."
        ),
    ),
    # ── Abschnitt C VI — Sonographische Leistungen ─────────────────────────────────────────────
    Provision(
        key="c_sono_organ_mutual",
        kind="mutual",
        cite_in="ab_10",
        legal_basis="GOÄ Allgemeine Bestimmungen zu Abschnitt C VI, Nr. 3",
        quote="Leistungen nach den Nummern 410 bis 418 sind nicht nebeneinander berechnungsfähig.",
        left=("410", "bis", "418"),
    ),
    Provision(
        key="c_sono_echo_mutual",
        kind="mutual",
        cite_in="ab_10",
        legal_basis="GOÄ Allgemeine Bestimmungen zu Abschnitt C VI, Nr. 4",
        quote="Die Leistungen nach den Nummern 422 bis 424 sind nicht nebeneinander berechnungsfähig.",
        left=("422", "bis", "424"),
    ),
    # ── Abschnitt C VIII — Zuschläge zu ambulanten Operationen ─────────────────────────────────
    Provision(
        key="c_ambop_verweilen",
        kind="mutual",
        cite_in="ab_11",
        legal_basis=(
            "GOÄ Allgemeine Bestimmungen zu Abschnitt C VIII, Nr. 4 i.V.m. GOÄ Anmerkungen zu "
            "den Nummern 448 und 449"
        ),
        quote=(
            "Neben den Leistungen nach Nummer 448 oder 449 darf die Leistung nach Nummer 56 nicht "
            "berechnet werden."
        ),
        left=("448", "449"),
        right=("56",),
        note=(
            "**Mutual because the two official sentences about this pair disagree about which "
            "side loses.** The Allgemeine Bestimmung quoted above is form E — 'Neben … 448 oder "
            "449 darf die Leistung nach Nummer 56 nicht berechnet werden' — so GOÄ 56 is the one "
            "that may not be charged. The Anmerkung printed under GOÄ 448 is form A and says the "
            "opposite: 'Der Zuschlag nach Nummer 448 ist neben den Leistungen nach den Nummern 1 "
            "bis 8 und 56 sowie dem Zuschlag nach Nummer 449 nicht berechnungsfähig.' Both are "
            "the official text and both agree the two positions may not stand together; they "
            "differ only on which one is dropped. Encoding either as one-way would pick a winner "
            "the GOÄ does not pick, and encoding both would leave LAYER 3 firing neither (it only "
            "decides a one-way edge when the opposite edge is absent). `mutual` says exactly what "
            "is certain — that this is a conflict — and hands the choice to the arbitrator, where "
            "it surfaces on the report instead of being silently resolved in the data."
        ),
    ),
    Provision(
        key="c_ambop_nachbeobachtung_mutual",
        kind="mutual",
        cite_in="ziffer:448",
        legal_basis="GOÄ Anmerkung zu Nummer 448",
        quote=(
            "Der Zuschlag nach Nummer 448 ist neben den Leistungen nach den Nummern 1 bis 8 und "
            "56 sowie dem Zuschlag nach Nummer 449 nicht berechnungsfähig."
        ),
        left=("448",),
        right=("449",),
        note=(
            "GOÄ 449's own Anmerkung states the same thing with the two swapped ('Der Zuschlag "
            "nach Nummer 449 ist neben … dem Zuschlag nach Nummer 448 nicht berechnungsfähig'), "
            "so the pair is mutual by both sentences rather than by inference."
        ),
    ),
    Provision(
        key="c_ambop_nachbeobachtung_beratung",
        kind="one_way",
        form="A",
        cite_in="ziffer:448",
        legal_basis="GOÄ Anmerkung zu Nummer 448",
        quote=(
            "Der Zuschlag nach Nummer 448 ist neben den Leistungen nach den Nummern 1 bis 8 und "
            "56 sowie dem Zuschlag nach Nummer 449 nicht berechnungsfähig."
        ),
        left=("448",),
        right=("1", "bis", "8"),
        note=(
            "Form A: the Zuschlag is the sentence's subject, so GOÄ 448 is what may not be "
            "charged beside a consultation or examination. GOÄ 56 and 449 are handled by the two "
            "provisions above — 56 because a second official sentence contradicts this one about "
            "it, 449 because it is symmetric — leaving only the 1–8 limb here."
        ),
    ),
    Provision(
        key="c_ambop_nachbeobachtung_beratung_449",
        kind="one_way",
        form="A",
        cite_in="ziffer:449",
        legal_basis="GOÄ Anmerkung zu Nummer 449",
        quote=(
            "Der Zuschlag nach Nummer 449 ist neben den Leistungen nach den Nummern 1 bis 8 und "
            "56 sowie dem Zuschlag nach Nummer 448 nicht berechnungsfähig."
        ),
        left=("449",),
        right=("1", "bis", "8"),
    ),
    # ── Abschnitt L III — Gelenkchirurgie ──────────────────────────────────────────────────────
    Provision(
        key="l_arthroskopie_punktion",
        kind="one_way",
        cite_in="ab_17",
        legal_basis="GOÄ Allgemeine Bestimmungen zu Abschnitt L III",
        quote=(
            "Neben den Leistungen nach den Nummern 2189 bis 2196 sind die Leistungen nach den "
            "Nummern 300 bis 302 sowie 3300 nicht berechnungsfähig."
        ),
        left=("2189", "bis", "2196"),
        right=("300", "bis", "302", "3300"),
    ),
    # ── Abschnitt M III 9 — Antikörper gegen körperfremde Antigene ─────────────────────────────
    Provision(
        key="m_ige_allergen",
        kind="one_way",
        cite_in="ab_29",
        legal_basis="GOÄ Allgemeine Bestimmung zu Abschnitt M III 9",
        quote=(
            "Neben den Leistungen nach den Nummer 3892, 3893 nd/oder 3894 sind die Leistungen "
            "nach den ummern 3572, 3890 und/oder 3891 nicht errechnungsfähig."
        ),
        left=("3892", "3893", "3894"),
        right=("3572", "3890", "3891"),
        note=(
            "Quoted with the official XML's OCR defects intact ('Nummer' for 'Nummern', 'nd/oder', "
            "'ummern', 'errechnungsfähig'). The six Ziffer numbers are unaffected by them."
        ),
    ),
    # ── Abschnitt O I 1 — Strahlendiagnostik, Skelett ──────────────────────────────────────────
    Provision(
        key="o_skelett_ganzkoerper",
        kind="one_way",
        cite_in="ab_40",
        legal_basis="GOÄ Allgemeine Bestimmung zu Abschnitt O I 1 (Skelett)",
        quote=(
            "Neben den Leistungen nach den Nummern 5050, 5060 und 5070 sind die Leistungen nach "
            "den Nummern 300 bis 302, 372, 373, 490, 491 und 5295 nicht berechnungsfähig."
        ),
        left=("5050", "5060", "5070"),
        right=("300", "bis", "302", "372", "373", "490", "491", "5295"),
    ),
    # ── Abschnitt O II — Nuklearmedizin ────────────────────────────────────────────────────────
    Provision(
        key="o_nuklear_5473_5481",
        kind="mutual",
        cite_in="ab_45",
        legal_basis="GOÄ Allgemeine Bestimmungen zu Abschnitt O II, Nr. 2",
        quote="Die Leistungen nach den Nummern 5473 und 5481 dürfen nicht nebeneinander berechnet werden.",
        left=("5473", "5481"),
    ),
    Provision(
        key="o_ergaenzung_cap",
        kind="factor_cap",
        cite_in="ab_46",
        legal_basis="GOÄ Allgemeine Bestimmung zu Abschnitt O II (Ergänzungsleistungen)",
        quote=(
            "Die Ergänzungsleistungen nach den Nummern 5480 bis 5485 sind nur mit dem einfachen "
            "Gebührensatz berechnungsfähig."
        ),
        left=("5480", "bis", "5485"),
        max_factor="1.0",
    ),
    # ── Anmerkung zu GOÄ 435 — stationäre Intensivbehandlung ───────────────────────────────────
    Provision(
        key="c_intensiv_435",
        kind="one_way",
        cite_in="ziffer:435",
        legal_basis="GOÄ Anmerkung zu Nummer 435",
        quote=(
            "Neben der Leistung nach Nummer 435 sind für die Dauer der stationären "
            "intensivmedizinischen Überwachung und Behandlung Leistungen nach den Abschnitten C "
            "III und M sowie die Leistungen nach den Nummern 1 bis 56, 61 bis 96, 200 bis 211, "
            "247, 250 bis 268, 270 bis 286a, 288 bis 298, 401 bis 424, 427 bis 433, 483 bis 485, "
            "488 bis 490, 500, 501, 505, 600 bis 609, 634 bis 648, 650 bis 657, 659 bis 661, 665 "
            "bis 672, 1529 bis 1532, 1728 bis 1733 und 3055 nicht berechnungsfähig."
        ),
        left=("435",),
        right=(
            "1", "bis", "56", "61", "bis", "96", "200", "bis", "211", "247", "250", "bis", "268",
            "270", "bis", "286a", "288", "bis", "298", "401", "bis", "424", "427", "bis", "433",
            "483", "bis", "485", "488", "bis", "490", "500", "501", "505", "600", "bis", "609",
            "634", "bis", "648", "650", "bis", "657", "659", "bis", "661", "665", "bis", "672",
            "1529", "bis", "1532", "1728", "bis", "1733", "3055",
        ),
        note=(
            "Only the numeric enumeration is encoded. The same sentence's other limb — 'Leistungen "
            "nach den Abschnitten C III und M' — names two whole Abschnitte, and this repo has no "
            "subsection-boundary table to expand 'C III' from; batch 1 held 435 back entirely for "
            "that reason. Encoding the numbers alone is strictly narrower than the sentence, never "
            "wider, and the Abschnitt limb stays quarantined."
        ),
    ),
)

# ==================================================================================================
# Mechanical from here down.
# ==================================================================================================

RANGE_TOKEN = "bis"
#: A Ziffer written with a letter suffix, e.g. `286a`. Only matters as a range endpoint.
SUFFIXED = re.compile(r"^(\d+)([a-z])$")


def _norm(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text or "").split())


def expand(tokens: tuple[str, ...], catalog: set[str]) -> list[str]:
    """Token list → the Ziffern it names that exist in the loaded catalog.

    ``("804", "bis", "812")`` expands to every **plain-numbered** Ziffer from 804 through 812.
    A letter-suffixed Ziffer inside a range (`250a` inside "250 bis 268") is *not* pulled in: the
    range is written in plain numbers, reading a suffixed sibling into it is an interpretation,
    and `docs/content/coverage-sprint-report-batch3.md` §4 quarantines the four the catalog has.
    A suffix written *in the sentence* (`286a`, as the endpoint of "270 bis 286a") is taken at
    face value, because there the source names it.
    """
    out: list[str] = []
    seen: set[str] = set()

    def add(ziffer: str) -> None:
        if ziffer in catalog and ziffer not in seen:
            seen.add(ziffer)
            out.append(ziffer)

    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token == RANGE_TOKEN:
            raise ValueError(f"'{RANGE_TOKEN}' with no left endpoint in {tokens!r}")
        if index + 1 < len(tokens) and tokens[index + 1] == RANGE_TOKEN:
            end_token = tokens[index + 2]
            suffix = SUFFIXED.match(end_token)
            end_number = int(suffix.group(1)) if suffix else int(end_token)
            for number in range(int(token), end_number + 1):
                add(str(number))
            if suffix:
                add(end_token)
            index += 3
            continue
        add(token)
        index += 1
    return out


def pairs(provision: Provision, catalog: set[str]) -> list[tuple[str, str, str, bool]]:
    """`(from_ziffer, to_ziffer, direction, uses_reverse_citation)` for one exclusion provision."""
    left = expand(provision.left, catalog)
    right = expand(provision.right, catalog) if provision.right else []
    out: list[tuple[str, str, str, bool]] = []
    if provision.kind == "one_way":
        #: `exclusion(rule, A, B, 0)` in `logic/datalog/goae_rules.dl` reads "if A is charged, B is
        #: not chargeable", so `from_ziffer` is always the position that *survives*. In a form-A
        #: sentence that is the second group, not the first.
        survives, blocked = (right, left) if provision.form == "A" else (left, right)
        for a in survives:
            for b in blocked:
                if a != b:
                    out.append((a, b, "one_way", False))
        return out
    #: A mutual provision with no `right` is a clique over `left`; with one, it is every
    #: cross pair. Both directions are written, which is how `RuleStore` reads a mutual pair.
    if right:
        for a in left:
            for b in right:
                if a != b:
                    out.extend([(a, b, "mutual", False), (b, a, "mutual", True)])
        return out
    for i, a in enumerate(left):
        for b in left[i + 1 :]:
            out.extend([(a, b, "mutual", False), (b, a, "mutual", False)])
    return out


def _cite_haystack(provision: Provision, catalog_raw: dict, ab: dict) -> tuple[str, str]:
    """`(where, normalised text)` the provision's quote must appear inside."""
    if provision.cite_in.startswith("ziffer:"):
        ziffer = provision.cite_in.split(":", 1)[1]
        entry = catalog_raw[ziffer]
        parts = [entry.get("official_text", ""), *(entry.get("annotations") or [])]
        return f"goae.official.json::{ziffer}", _norm(" ||| ".join(parts))
    text = ab[provision.cite_in]
    return f"allgemeine_bestimmungen.json::{provision.cite_in}", _norm(text)


def already_capped(path: Path) -> dict[str, str]:
    """Ziffer → rule_id, for the factor caps this file already carries outside batch 3.

    `app.solvers.souffle_facts` emits one `factor_cap` fact per row, so two rows capping the same
    Ziffer would put two facts in the program and leave it to fact ordering which `rule_id` a
    finding cites. Batch 3 therefore yields to whatever is already there — GOÄ 102, 401, 404–406
    and 440–449 are all capped at 1.0 already, by auto-extracted rows quoting the *Anmerkung* that
    says the same thing as the Allgemeine Bestimmung quoted here. Skipping them changes no
    enforcement; it only keeps one citation per Ziffer.
    """
    if not path.exists():
        return {}
    with path.open(encoding="utf-8", newline="") as handle:
        return {
            row["ziffer"]: row["rule_id"]
            for row in csv.DictReader(handle)
            if f"_{BATCH}_" not in (row.get("rule_id") or "")
        }


def build_rows(
    catalog: set[str], catalog_raw: dict, ab: dict, prior_caps: dict[str, str] | None = None
) -> tuple[list[dict], list[dict], list[tuple[str, str]]]:
    prior_caps = prior_caps or {}
    exclusions: list[dict] = []
    factor_caps: list[dict] = []
    ceded: list[tuple[str, str]] = []
    seen_ids: set[str] = set()
    for provision in PROVISIONS:
        where, haystack = _cite_haystack(provision, catalog_raw, ab)
        if _norm(provision.quote) not in haystack:
            raise SystemExit(
                f"{provision.key}: quote is not verbatim in {where}\n  {_norm(provision.quote)[:120]}"
            )
        if provision.reverse_quote:
            reverse_where = provision.reverse_cite_in or provision.cite_in
            if _norm(provision.reverse_quote) not in _norm(ab[reverse_where]):
                raise SystemExit(
                    f"{provision.key}: reverse_quote is not verbatim in {reverse_where}"
                )
        if provision.kind == "factor_cap":
            for ziffer in expand(provision.left, catalog):
                if ziffer in prior_caps:
                    ceded.append((ziffer, prior_caps[ziffer]))
                    continue
                rule_id = f"cap_{BATCH}_{ziffer}"
                if rule_id in seen_ids:
                    raise SystemExit(f"duplicate rule_id {rule_id}")
                seen_ids.add(rule_id)
                factor_caps.append(
                    {
                        "rule_id": rule_id,
                        "ziffer": ziffer,
                        "max_factor": provision.max_factor,
                        "legal_basis": provision.legal_basis,
                        "quote": provision.quote,
                        "verified": "true",
                        "verified_at": VERIFIED_AT,
                        "source": SOURCE,
                        "ai_verdict": "",
                        "ai_reasoning": "",
                        "ai_model": "",
                        "ai_checked_at": "",
                    }
                )
            continue
        for a, b, direction, reversed_side in pairs(provision, catalog):
            reverse = reversed_side and bool(provision.reverse_quote)
            rule_id = f"excl_{BATCH}_{a}_{b}"
            if rule_id in seen_ids:
                raise SystemExit(f"duplicate rule_id {rule_id} (provision {provision.key})")
            seen_ids.add(rule_id)
            exclusions.append(
                {
                    "rule_id": rule_id,
                    "from_ziffer": a,
                    "to_ziffer": b,
                    "direction": direction,
                    "legal_basis": (
                        provision.reverse_legal_basis if reverse else provision.legal_basis
                    ),
                    "quote": provision.reverse_quote if reverse else provision.quote,
                    "verified": "true",
                    "verified_at": VERIFIED_AT,
                    "source": SOURCE,
                }
            )
    return exclusions, factor_caps, ceded


def _rewrite(path: Path, new_rows: list[dict], infix: str) -> str:
    """Existing file with its batch-3 rows replaced by `new_rows`, as text."""
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        kept = [row for row in reader if infix not in (row.get("rule_id") or "")]
    unknown = {key for row in new_rows for key in row} - set(fieldnames)
    if unknown:
        raise SystemExit(f"{path.name}: generated columns not in header: {sorted(unknown)}")
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for row in kept + [{key: row.get(key, "") for key in fieldnames} for row in new_rows]:
        writer.writerow(row)
    return buffer.getvalue()


def coverage(rules_dir: Path) -> tuple[int, int]:
    """`(Ziffern under an enforced public-family rule, catalog size)` — the published definition."""

    def rows(name: str) -> list[dict]:
        path = rules_dir / name
        return list(csv.DictReader(path.open(encoding="utf-8"))) if path.exists() else []

    def truthy(value: str | None) -> bool:
        return str(value or "").strip().lower() in {"true", "1", "yes", "y"}

    under: set[str] = set()
    for row in rows("exclusions.csv") + rows("exclusions.manual.csv"):
        if truthy(row["verified"]):
            under.update([row["from_ziffer"], row["to_ziffer"]])
    for row in rows("zielleistung.csv") + rows("zielleistung.manual.csv"):
        if truthy(row["verified"]):
            under.update([row["parent_ziffer"], row["child_ziffer"]])
    for row in rows("specificity.csv") + rows("specificity.manual.csv"):
        if truthy(row["verified"]):
            under.update([row["specific_ziffer"], row["general_ziffer"]])
    for row in rows("factor_caps.csv") + rows("factor_caps.manual.csv"):
        if truthy(row["verified"]):
            under.add(row["ziffer"])
    under.discard("")
    total = len(json.loads(CATALOG.read_text(encoding="utf-8"))["ziffern"])
    return len(under), total


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="exit 1 if a file would change")
    parser.add_argument("--report", action="store_true", help="print the coverage delta only")
    args = parser.parse_args(argv)

    catalog_payload = json.loads(CATALOG.read_text(encoding="utf-8"))
    catalog_raw = {entry["ziffer"]: entry for entry in catalog_payload["ziffern"]}
    catalog = set(catalog_raw)
    ab_payload = json.loads(PROVISIONS_JSON.read_text(encoding="utf-8"))
    ab = {provision["id"]: provision["text"] for provision in ab_payload["provisions"]}

    before = coverage(RULES_DIR)
    exclusions, factor_caps, ceded = build_rows(
        catalog, catalog_raw, ab, already_capped(FACTOR_CAPS_FILE)
    )
    planned = {
        EXCLUSIONS_FILE: _rewrite(EXCLUSIONS_FILE, exclusions, f"_{BATCH}_"),
        FACTOR_CAPS_FILE: _rewrite(FACTOR_CAPS_FILE, factor_caps, f"_{BATCH}_"),
    }

    if args.check:
        stale = [p.name for p, text in planned.items() if p.read_text(encoding="utf-8") != text]
        if stale:
            print(f"STALE: {', '.join(stale)} — re-run without --check", file=sys.stderr)
            return 1
        print(f"batch 3 rows up to date ({len(exclusions)} exclusions, {len(factor_caps)} caps)")
        return 0

    if not args.report:
        for path, text in planned.items():
            path.write_text(text, encoding="utf-8")

    after = coverage(RULES_DIR)
    touched = {row["ziffer"] for row in factor_caps}
    for row in exclusions:
        touched.update([row["from_ziffer"], row["to_ziffer"]])
    print(f"provisions      {len(PROVISIONS)}")
    print(f"exclusion rows  {len(exclusions)}")
    print(f"factor-cap rows {len(factor_caps)}")
    print(f"Ziffern named   {len(touched)}")
    if ceded:
        print(f"caps ceded      {len(ceded)} already capped elsewhere: "
              f"{', '.join(f'{z} ({rule})' for z, rule in ceded)}")
    print(f"coverage        {before[0]}/{before[1]} -> {after[0]}/{after[1]} "
          f"({before[0] / before[1]:.2%} -> {after[0] / after[1]:.2%})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
