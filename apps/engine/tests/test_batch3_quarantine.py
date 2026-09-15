"""The batch-3 quarantine list from `docs/content/coverage-sprint-report-batch3.md` §4, enforced.

Batch 3 read 66 constraint sentences in the GOÄ's 50 *Allgemeine Bestimmungen* plus 29 Ziffer
annotations the deterministic extractor had left unencoded, and shipped rules for nineteen of
them. The rest were held out for a stated reason.

`tests/test_batch2_quarantine.py` says why a list like this is worth executing, and the argument
is the same one here:

    A quarantine that lives only in prose decays: the next batch re-runs the same scan, sees the
    same sentence, and has nothing that says "this one was looked at and rejected, here is why."

Batch 3 adds a second reason. Its rows are *generated* — one `PROVISIONS` entry in
`scripts/build_batch3_rules.py` can emit 182 of them — so the cost of a moment's optimism about a
conditional sentence is not one wrong row, it is a family. Every marker below is a verbatim
fragment of the sentence that was rejected, checked against the shipped quotes: if a later batch
encodes one of these, its citation will contain the marker and this file fails with the reason the
sentence was rejected in the first place.

Three checks:

  * **not quoted** — no shipped batch-3 rule cites a quarantined sentence;
  * **not executed** — the pairs those sentences would have produced draw no batch-3 block from
    the real engine;
  * **the markers are real** — every fragment below is verbatim in the official source, so a typo
    in this file cannot turn a check into a no-op that passes forever.
"""

from __future__ import annotations

import csv
import json

import pytest

from app.config import CATALOG_DIR, RULES_DATA_DIR
from tests.conftest import make_extraction, one_act_per_ziffer

BATCH_INFIX = "_b3_"

# ==============================================================================================
# §4 of the report, transcribed. Grouped by the reason, because the reason is the content.
# ==============================================================================================

#: Scope is an *Abschnitt*, not a list of numbers. This repo has no table mapping "Abschnitt C III"
#: or "M III 13" to its member Ziffern, and inventing one to expand a rule that would then touch
#: hundreds of positions is the largest single-step guess available in this data. Batch 1 held
#: GOÄ 435 back for exactly this; batch 3 encodes only 435's *numeric* limb and leaves this one.
ABSCHNITT_SCOPE: dict[str, str] = {
    "sind Leistungen nach Abschnitt M - mit Ausnahme von Leistungen nach den Abschnitten M III 13": (
        "GOÄ 437 — a whole Abschnitt minus two named subsections"
    ),
    "Leistungen nach den Abschnitten B und C (mit Ausnahme der Leistung nach Nummer 50": (
        "GOÄ 793 — two whole Abschnitte with a carve-out, plus a named list"
    ),
    "neben Leistungen nach den Abschnitten C bis O im Behandlungsfall nur einmal berechnungsfähig": (
        "Abschnitt B AB Nr. 2 — thirteen Abschnitte, and a Behandlungsfall window on top"
    ),
}

#: Conditioned on something an invoice line does not carry. The engine sees Ziffern, factors,
#: dates and a patient; it does not see who held the scalpel, which joint was operated on, whether
#: the specimen was the same one, or where the analyser stood.
INVISIBLE_CONDITION: dict[str, str] = {
    "Die Zuschläge nach den Buchstaben B bis D dürfen von Krankenhausärzten nicht berechnet werden": (
        "who rendered the service (and an 'es sei denn' on top)"
    ),
    "sind für Besuche von Krankenhaus- und Belegärzten im Krankenhaus nicht berechnungsfähig": (
        "who rendered the service"
    ),
    "sind nicht berechnungsfähig, wenn der Patient an demselben Tag wegen derselben Erkrankung in "
    "stationäre Krankenhausbehandlung aufgenommen wird": "a later admission, with its own exception",
    "an demselben Gelenk im Rahmen derselben Sitzung erbracht": "which joint",
    "sind für operative Eingriffe an demselben Gelenk im Rahmen derselben Sitzung jeweils nur "
    "einmal berechnungsfähig": "which joint, plus a per-Sitzung window",
    "sind nicht berechnungsfähig, wenn sie in einem Krankenhaus": "where the analysis was run",
    "sind nicht mehrfach berechnungsfähig, wenn anstelle einer Mischung": "how the drugs were given",
    "Die Leistung nach Nummer 60 ist nicht berechnungsfähig, wenn die Ärzte Mitglieder derselben "
    "Krankenhausabteilung": "the practice relationship between two doctors",
    "Die Leistung nach Nummer 261 ist im Zusammenhang mit einer Anästhesie/Narkose nicht "
    "berechnungsfähig": "what was injected",
    "Die Leistung nach Nummer 1532 ist im Zusammenhang mit einer Intubationsnarkose nicht "
    "berechnungsfähig": "whether an intubation narcosis was running",
    "Wird eine Harnblasenkatheterisierung lediglich ausgeführt": "why the catheter was placed",
    "ist die Leistung nach Nummer 4850 bei Untersuchungen aus demselben Material nicht "
    "berechnungsfähig": "whether it was the same specimen — batch 1 held this one too",
    "ist nicht berechnungsfähig für Untersuchungen des Harntrakts": "which organ was imaged",
}

#: A window `QuantityLimitRule` cannot evaluate. `patient_history.behandlungsfall_bounds` computes
#: a calendar quarter and nothing else, so "je Sitzung" (tighter) and "je Behandlungstag" /
#: "je Basisleistung" / "insgesamt" (different) would all be enforced at the wrong width — the
#: exact line batch 2 §4 drew, redrawn here rather than relitigated.
UNSUPPORTED_WINDOW: dict[str, str] = {
    "sowie 422 bis 424 sind je Sitzung jeweils nur einmal berechnungsfähig": "sonography, je Sitzung",
    "können jeweils nur einmal je Behandlungstag berechnet werden": "infusions, je Behandlungstag",
    "unabhängig von der Anzahl der Ebenen, Projektionen, Durchleuchtungen bzw. Serien insgesamt "
    "jeweils nur einmal berechnet werden": "radiology, 'insgesamt'",
    "5338 und 5339 sind je Sitzung jeweils nur einmal berechnungsfähig": "angiography, je Sitzung",
    "Die Leistungen nach den Nummern 5345 bis 5356 können je Sitzung nur einmal berechnet werden": (
        "interventional radiology, je Sitzung"
    ),
    "Die Leistungen nach den Nummern 5369 bis 5375 sind je Sitzung jeweils nur einmal "
    "berechnungsfähig": "CT, je Sitzung",
    "sind je Basisleistung oder zulässiger Wiederholungsuntersuchung nur einmal berechnungsfähig": (
        "nuclear medicine, je Basisleistung"
    ),
    "Die Leistungen nach den Nummern 5700 bis 5735 sind je Sitzung jeweils nur einmal "
    "berechnungsfähig": "MRI, je Sitzung",
    "Neben der Leistung nach Nummer 15 ist die Leistung nach Nummer 4 im Behandlungsfall nicht "
    "berechnungsfähig": "a Behandlungsfall window on an otherwise clean pair",
}

#: The other side of the relation is described, not numbered. Mapping a description to a Ziffer is
#: the guess batch 1 refused for GOÄ 1056 and 1532 and this batch refuses in the same words.
DESCRIBED_NOT_NUMBERED: dict[str, str] = {
    "Wundverbände nach Nummer 200, die im Zusammenhang mit einer operativen Leistung": (
        "'eine operative Leistung' — the four pairs that *are* named sit in zielleistung.manual.csv"
    ),
    "Gegebenenfalls erforderliche Gefäßpunktionen sind Bestandteil der Leistungen nach den "
    "Nummern 270 bis 287": "'Gefäßpunktionen' is an act, not a Ziffer",
    "Die zur Einbringung des Kontrastmittels erforderlichen Maßnahmen": "a list of acts",
    "Die Befundmitteilung oder der einfache Befundbericht mit Angaben zu Befund(en) und zur "
    "Diagnose ist Bestandteil": "an act",
    "Die Beurteilung von Röntgenaufnahmen (auch Fremdaufnahmen) als selbständige Leistung ist "
    "nicht berechnungsfähig": "an act",
    "neben einer Gebühr für die quantitative Immunfluoreszenzuntersuchung": (
        "a method, applying across a whole Katalog with no Ziffer named"
    ),
    "Die Leistung nach Nummer 61 ist neben anderen Leistungen nicht berechnungsfähig": (
        "'anderen Leistungen' is everything — batch 1 held this too"
    ),
    "ist die intravaginale oder intrazervikale Applikation von Prostaglandin-Gel nicht gesondert "
    "berechnungsfähig": "a drug, not a Ziffer — batch 1 held this too",
    "Terminvereinbarungen sind nicht berechnungsfähig": "not a Ziffer at all",
}

#: Real, unconditional, numbered — and not an exclusion. A fee *reduction*, a "highest-valued one
#: wins" selection, a Höchstwert ceiling. Each would need a rule table this engine does not have,
#: which is a schema decision and not a data-entry one (batch 1 §6, batch 2 §4).
NO_RULE_TABLE: dict[str, str] = {
    "die Vergütungssätze der weiteren Eingriffe sind deshalb um den Vergütungssatz nach Nummer": (
        "reduces a fee by another Ziffer's fee; nothing here can express that"
    ),
    "ist nur die jeweils höchstbewertete dieser Leistungen berechnungsfähig": (
        "keep-the-dearest over a set, decided by Punktzahl — no table for it"
    ),
    "Sind diese Einzelschritte methodisch notwendige Bestandteile": (
        "the Zielleistungsprinzip stated in general; `zielleistung.csv` holds pairs"
    ),
    "so kann er nur das niedriger bewertete Verfahren abrechnen": (
        "keep-the-cheaper over clinically equivalent methods, which are not enumerated"
    ),
    "dürfen Ergänzungsleistungen für Quantifizierungen nicht zusätzlich berechnet werden": (
        "conditioned on what the Basisleistung contained"
    ),
    "nicht mehr als zwei Verfahren nach den Nummern 4666 bis 4671": (
        "a cumulative cap across six codes — batch 2 quarantined GOÄ 391 for this shape"
    ),
}

#: Two quarantined limbs sit inside sentences that *are* encoded, for their other limb. Their
#: markers cannot go in the groups above: the citation is the whole sentence, verbatim, so the
#: marker is in the shipped quote by construction. What must hold instead is that the limb added
#: no Ziffern — checked below against the exact set each provision is allowed to name.
PARTIALLY_ENCODED: dict[str, tuple[str, str]] = {
    "c_intensiv_435": (
        "Leistungen nach den Abschnitten C III und M sowie die Leistungen",
        "the sentence's twenty-one numeric ranges are encoded; 'Abschnitte C III und M' is not",
    ),
    "c_impfung_beratung": (
        "die gegebenenfalls erforderliche Eintragung in den Impfpaß",
        "'Nummern 1 und 2' is encoded; the Impfpaß entry names an act, not a Ziffer",
    ),
}

#: What GOÄ 435's Abschnitt limb would have added, had it been expanded: Abschnitt M laboratory
#: positions and the Abschnitt C III punctures. None may be a `to_ziffer` of a batch-3 435 rule.
#: (GOÄ 300–321 *are* Abschnitt C III and are likewise absent — 435's numeric list stops at 298.)
ABSCHNITT_LIMB_WOULD_HAVE_ADDED = ("3550", "4530", "4851", "300", "301", "302", "315")

QUARANTINED: dict[str, dict[str, str]] = {
    "scope is an Abschnitt, not a list of numbers": ABSCHNITT_SCOPE,
    "conditioned on something an invoice does not carry": INVISIBLE_CONDITION,
    "window this engine cannot evaluate": UNSUPPORTED_WINDOW,
    "the other side is described, not numbered": DESCRIBED_NOT_NUMBERED,
    "real and unconditional, but no rule table exists for its shape": NO_RULE_TABLE,
}

#: Pairs a quarantined sentence would have produced, had it been encoded. Claiming both Ziffern
#: must draw no batch-3 block. Each is (surviving-side, other-side, which entry it comes from).
QUARANTINED_PAIRS: tuple[tuple[str, str, str], ...] = (
    ("437", "3550", "GOÄ 437's Abschnitt-M limb"),
    ("15", "4", "the Behandlungsfall window on 15 → 4"),
    ("61", "1", "GOÄ 61's 'neben anderen Leistungen'"),
    ("2192", "2195", "the per-Sitzung, same-joint cap in Abschnitt L III"),
    ("5345", "5346", "the per-Sitzung cap on interventional radiology"),
    ("5700", "5705", "the per-Sitzung cap on MRI"),
    ("4850", "4851", "the same-specimen condition batch 1 also held"),
    ("200", "2000", "the Verband provision's descriptive limb"),
)

#: Letter-suffixed Ziffern that sit numerically inside one of GOÄ 435's plainly-numbered ranges.
#: 286a is *not* here: the sentence names it as a range endpoint ("270 bis 286a"), which is the
#: evidence the other three lack — and is itself the reason reading them in would be a guess.
SUFFIXED_NOT_SWEPT_IN = ("250a", "265a", "605a")


@pytest.fixture(scope="module")
def batch3_quotes() -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for name in ("exclusions.manual.csv", "factor_caps.csv"):
        with (RULES_DATA_DIR / name).open(encoding="utf-8", newline="") as handle:
            rows += [
                (r["rule_id"], r["quote"])
                for r in csv.DictReader(handle)
                if BATCH_INFIX in r["rule_id"]
            ]
    assert rows, "no batch-3 rows found — every check in this file would be vacuous"
    return rows


@pytest.fixture(scope="module")
def official_text() -> str:
    provisions = json.loads(
        (CATALOG_DIR / "allgemeine_bestimmungen.json").read_text(encoding="utf-8")
    )
    catalog = json.loads((CATALOG_DIR / "goae.official.json").read_text(encoding="utf-8"))
    parts = [p["text"] for p in provisions["provisions"]]
    for entry in catalog["ziffern"]:
        parts.append(entry.get("official_text", ""))
        parts.extend(entry.get("annotations") or [])
    return " ||| ".join(" ".join(part.split()) for part in parts)


@pytest.mark.parametrize("reason", sorted(QUARANTINED))
def test_every_quarantine_marker_is_verbatim_in_the_official_source(reason, official_text):
    """A typo here would silently turn its check below into one that can never fail."""
    absent = [
        marker for marker in QUARANTINED[reason] if " ".join(marker.split()) not in official_text
    ]
    assert absent == [], f"quarantine markers not found in the official source: {absent}"


@pytest.mark.parametrize("reason", sorted(QUARANTINED))
def test_no_shipped_batch3_rule_cites_a_quarantined_sentence(reason, batch3_quotes):
    encoded = [
        (rule_id, detail)
        for marker, detail in QUARANTINED[reason].items()
        for rule_id, quote in batch3_quotes
        if " ".join(marker.split()) in " ".join(quote.split())
    ]
    assert encoded == [], (
        f"batch-3 rules cite sentences quarantined as {reason!r}: {encoded[:3]}"
    )


@pytest.mark.parametrize("a,b,why", QUARANTINED_PAIRS)
def test_a_quarantined_pair_draws_no_batch3_block(souffle, a, b, why):
    """The half that catches an accidental re-encoding: a "no rule exists" assertion stops being
    informative the moment somebody adds the rule, and this one does not."""
    result = souffle.run(make_extraction(), one_act_per_ziffer(a, b))

    from_batch3 = [
        (x.ziffer, x.rule_id) for x in result.blocked if (x.rule_id or "").startswith("excl_b3_")
    ]
    assert from_batch3 == [], f"{why}: batch 3 blocked {from_batch3} on GOÄ {a} + {b}"


@pytest.mark.parametrize("ziffer", SUFFIXED_NOT_SWEPT_IN)
def test_a_suffixed_sibling_inside_a_435_range_is_named_by_no_batch3_rule(ziffer):
    with (RULES_DATA_DIR / "exclusions.manual.csv").open(encoding="utf-8", newline="") as handle:
        named = [
            r["rule_id"]
            for r in csv.DictReader(handle)
            if BATCH_INFIX in r["rule_id"] and ziffer in (r["from_ziffer"], r["to_ziffer"])
        ]
    assert named == [], (
        f"GOÄ {ziffer} is inside a plainly-numbered range but written nowhere in the sentence; "
        f"batch 3 does not read it in (report §4): {named[:3]}"
    )


def test_the_named_suffixed_endpoint_is_the_exception(batch3_quotes):
    """286a is encoded, and the contrast is the whole argument for the three above."""
    with (RULES_DATA_DIR / "exclusions.manual.csv").open(encoding="utf-8", newline="") as handle:
        named = [
            r["rule_id"]
            for r in csv.DictReader(handle)
            if BATCH_INFIX in r["rule_id"] and "286a" in (r["from_ziffer"], r["to_ziffer"])
        ]
    assert named == ["excl_b3_435_286a"], named


@pytest.mark.parametrize("key", sorted(PARTIALLY_ENCODED))
def test_a_partially_encoded_sentence_still_quotes_its_whole_self(key, batch3_quotes):
    """The citation is the sentence, not the half that was used.

    Trimming a quote down to the encoded limb would make every check in this repo pass and would
    hide, from the only person who could catch it, that the rule is narrower than the paragraph
    it names.
    """
    marker, _ = PARTIALLY_ENCODED[key]
    cited = [rid for rid, quote in batch3_quotes if " ".join(marker.split()) in " ".join(quote.split())]
    assert cited, f"{key}: no shipped rule quotes the full sentence including {marker!r}"


def test_the_435_abschnitt_limb_added_no_ziffern():
    with (RULES_DATA_DIR / "exclusions.manual.csv").open(encoding="utf-8", newline="") as handle:
        blocked_by_435 = {
            r["to_ziffer"]
            for r in csv.DictReader(handle)
            if BATCH_INFIX in r["rule_id"] and r["from_ziffer"] == "435"
        }
    assert blocked_by_435, "no batch-3 GOÄ 435 rules found — this check would be vacuous"
    leaked = sorted(set(ABSCHNITT_LIMB_WOULD_HAVE_ADDED) & blocked_by_435)
    assert leaked == [], (
        f"GOÄ 435 blocks {leaked}, which its numeric ranges do not reach — the 'Abschnitte C III "
        f"und M' limb is quarantined (report §4) and must add nothing"
    )


def test_the_vaccination_provision_named_only_the_two_ziffern_it_cites():
    with (RULES_DATA_DIR / "exclusions.manual.csv").open(encoding="utf-8", newline="") as handle:
        rows = [
            r
            for r in csv.DictReader(handle)
            if BATCH_INFIX in r["rule_id"]
            and r["legal_basis"] == "GOÄ Allgemeine Bestimmungen zu Abschnitt C V"
        ]
    assert {r["to_ziffer"] for r in rows} == {"1", "2"}
    assert {r["from_ziffer"] for r in rows} == {"376", "377", "378"}
