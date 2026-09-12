"""Tests for `scripts/validate_batch2_csvs.py`.

A validator nobody has ever seen fail is indistinguishable from a validator that always passes,
so every check that can fail is driven here against a deliberately broken copy of the real file.
The copies live in `tmp_path`; `data/rules/` is never written to.

The last test is the one that matters operationally: the real, shipped corpus must come back
clean at ERROR severity. If a future batch lands a row this validator rejects, that test is the
thing that says so.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ENGINE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ENGINE_ROOT.parents[1]
RULES_DIR = REPO_ROOT / "data" / "rules"
CATALOG = REPO_ROOT / "data" / "catalogs" / "goae_current" / "goae.official.json"

_spec = importlib.util.spec_from_file_location(
    "validate_batch2_csvs", ENGINE_ROOT / "scripts" / "validate_batch2_csvs.py"
)
validator_module = importlib.util.module_from_spec(_spec)
# Register before exec: `@dataclass` resolves annotations through `sys.modules[cls.__module__]`,
# which is None for a module built with `module_from_spec` and never installed.
sys.modules["validate_batch2_csvs"] = validator_module
_spec.loader.exec_module(validator_module)


@pytest.fixture(scope="module")
def catalog() -> dict[str, str]:
    return validator_module.load_catalog(CATALOG)


@pytest.fixture
def rules_copy(tmp_path: Path) -> Path:
    """A byte-identical copy of the four Batch 2 files, safe to mutate."""
    target = tmp_path / "rules"
    target.mkdir()
    for spec in validator_module.FAMILIES:
        (target / spec.filename).write_bytes((RULES_DIR / spec.filename).read_bytes())
    return target


def _run(rules_dir: Path, catalog: dict[str, str]):
    v = validator_module.Validator(rules_dir, catalog)
    code = v.run()
    return code, v


def _failures(v, check_prefix: str) -> list:
    return [f for f in v.findings if f.status == "FAIL" and f.check.startswith(check_prefix)]


def _rewrite(path: Path, mutate) -> None:
    """Read a family CSV, hand every row to `mutate`, write it back."""
    text = path.read_text(encoding="utf-8")
    reader = csv.DictReader(text.splitlines(True))
    fieldnames = list(reader.fieldnames or [])
    rows = [dict(r) for r in reader]
    mutate(rows)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


# ==============================================================================================
# The shipped corpus
# ==============================================================================================


def test_the_shipped_corpus_passes_at_error_severity(catalog):
    """`data/rules/` as committed must raise no ERROR. This is the release gate."""
    code, v = _run(RULES_DIR, catalog)
    errors = [f for f in v.findings if f.status == "FAIL" and f.severity == "ERROR"]
    assert errors == [], f"shipped corpus has ERROR findings: {[e.as_dict() for e in errors]}"
    assert code == 0


def test_the_shipped_corpus_row_counts_are_the_reported_ones(catalog):
    """13 + 15 + 9 + 0 = 37, the number `coverage-sprint-report-batch2.md` publishes."""
    _, v = _run(RULES_DIR, catalog)
    assert v.row_counts == {
        "quantity_limits.manual.csv": 13,
        "gender_restrictions.manual.csv": 15,
        "age_restrictions.manual.csv": 9,
        "time_relations.manual.csv": 0,
    }
    assert sum(v.row_counts.values()) == 37


def test_an_empty_family_file_is_valid_not_an_error(catalog):
    """`time_relations.manual.csv` ships with a header and no rows, on purpose."""
    _, v = _run(RULES_DIR, catalog)
    time_errors = [
        f
        for f in v.findings
        if f.file == "time_relations.manual.csv" and f.status == "FAIL" and f.severity == "ERROR"
    ]
    assert time_errors == []


# ==============================================================================================
# File-level checks
# ==============================================================================================


def test_a_missing_file_is_an_error(rules_copy, catalog):
    (rules_copy / "quantity_limits.manual.csv").unlink()
    code, v = _run(rules_copy, catalog)
    assert code == 1
    assert _failures(v, "file_exists")


def test_a_bom_is_an_error(rules_copy, catalog):
    path = rules_copy / "gender_restrictions.manual.csv"
    path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())
    code, v = _run(rules_copy, catalog)
    assert code == 1
    assert _failures(v, "no_bom")


def test_invalid_utf8_is_an_error(rules_copy, catalog):
    (rules_copy / "age_restrictions.manual.csv").write_bytes(b"rule_id,ziffer\n\xff\xfe,26\n")
    code, v = _run(rules_copy, catalog)
    assert code == 1
    assert _failures(v, "utf8_decodes")


def test_a_renamed_column_is_schema_drift(rules_copy, catalog):
    path = rules_copy / "quantity_limits.manual.csv"
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace("max_count", "maximum_count", 1), encoding="utf-8")
    code, v = _run(rules_copy, catalog)
    assert code == 1
    assert _failures(v, "header_exact")


def test_a_dropped_column_is_schema_drift(rules_copy, catalog):
    path = rules_copy / "gender_restrictions.manual.csv"
    _rewrite(path, lambda rows: None)  # normalise first
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace(",source", "", 1), encoding="utf-8")
    code, v = _run(rules_copy, catalog)
    assert code == 1
    assert _failures(v, "header_exact")


# ==============================================================================================
# Row-level checks
# ==============================================================================================


@pytest.mark.parametrize(
    ("filename", "column"),
    [
        ("quantity_limits.manual.csv", "quote"),
        ("quantity_limits.manual.csv", "legal_basis"),
        ("quantity_limits.manual.csv", "source"),
        ("gender_restrictions.manual.csv", "quote"),
        ("age_restrictions.manual.csv", "verified_at"),
    ],
)
def test_blanking_a_required_field_is_an_error(rules_copy, catalog, filename, column):
    _rewrite(rules_copy / filename, lambda rows: rows[0].update({column: ""}))
    code, v = _run(rules_copy, catalog)
    assert code == 1
    assert _failures(v, f"required:{column}")


@pytest.mark.parametrize("placeholder", ["TBD", "todo", "n/a", "---", "???"])
def test_a_placeholder_citation_is_an_error(rules_copy, catalog, placeholder):
    _rewrite(
        rules_copy / "quantity_limits.manual.csv",
        lambda rows: rows[0].update({"quote": placeholder}),
    )
    code, v = _run(rules_copy, catalog)
    assert code == 1
    assert _failures(v, "not_placeholder:quote")


def test_a_duplicate_rule_id_is_an_error(rules_copy, catalog):
    _rewrite(
        rules_copy / "gender_restrictions.manual.csv",
        lambda rows: rows[1].update({"rule_id": rows[0]["rule_id"]}),
    )
    code, v = _run(rules_copy, catalog)
    assert code == 1
    assert _failures(v, "rule_id_unique")


def test_two_rules_about_the_same_ziffer_is_an_error(rules_copy, catalog):
    def mutate(rows):
        rows[1]["ziffer"] = rows[0]["ziffer"]
        rows[1]["quote"] = rows[0]["quote"]
        rows[1]["legal_basis"] = rows[0]["legal_basis"]

    _rewrite(rules_copy / "gender_restrictions.manual.csv", mutate)
    code, v = _run(rules_copy, catalog)
    assert code == 1
    assert _failures(v, "no_duplicate_subject")


def test_a_ziffer_outside_the_catalog_is_an_error(rules_copy, catalog):
    _rewrite(
        rules_copy / "quantity_limits.manual.csv", lambda rows: rows[0].update({"ziffer": "99999"})
    )
    code, v = _run(rules_copy, catalog)
    assert code == 1
    assert _failures(v, "ziffer_in_catalog")


def test_a_control_character_in_a_cell_is_an_error(rules_copy, catalog):
    _rewrite(
        rules_copy / "age_restrictions.manual.csv",
        lambda rows: rows[0].update({"legal_basis": "GOÄ\tNr. 26"}),
    )
    code, v = _run(rules_copy, catalog)
    assert code == 1
    assert _failures(v, "no_control_chars")


# ==============================================================================================
# Citation fidelity — the check the legal claim rests on
# ==============================================================================================


def test_an_invented_quote_is_an_error(rules_copy, catalog):
    _rewrite(
        rules_copy / "quantity_limits.manual.csv",
        lambda rows: rows[0].update({"quote": "Diese Leistung ist niemals berechnungsfähig."}),
    )
    code, v = _run(rules_copy, catalog)
    assert code == 1
    assert _failures(v, "citation_verbatim")


def test_a_quote_tidied_by_one_character_is_an_error(rules_copy, catalog):
    """The catalog's GOÄ 382 text says "je Text" — an upstream typo. A row that silently
    corrects it to "je Test" is no longer quoting the catalog, and must not pass."""

    def mutate(rows):
        row = next(r for r in rows if r["ziffer"] == "382")
        row["quote"] = row["quote"].replace("je Text", "je Test")

    _rewrite(rules_copy / "quantity_limits.manual.csv", mutate)
    code, v = _run(rules_copy, catalog)
    assert code == 1
    assert _failures(v, "citation_verbatim")


def test_a_quote_from_a_different_ziffer_is_an_error(rules_copy, catalog):
    """Citing a real GOÄ sentence that belongs to some other Ziffer is still a fabrication."""

    def mutate(rows):
        by = {r["ziffer"]: r for r in rows}
        by["4"]["quote"] = by["380"]["quote"]

    _rewrite(rules_copy / "quantity_limits.manual.csv", mutate)
    code, v = _run(rules_copy, catalog)
    assert code == 1
    assert _failures(v, "citation_verbatim")


def test_a_multi_part_quote_fails_if_any_part_is_invented(rules_copy, catalog):
    """`age_man_26` cites two sentences joined by ' | '. One real part must not carry one fake."""

    def mutate(rows):
        row = next(r for r in rows if r["ziffer"] == "26")
        row["quote"] = row["quote"].split(" | ")[0] + " | Frei erfundener Satz ohne Quelle."

    _rewrite(rules_copy / "age_restrictions.manual.csv", mutate)
    code, v = _run(rules_copy, catalog)
    assert code == 1
    assert _failures(v, "citation_verbatim")


def test_whitespace_only_differences_in_a_quote_still_pass(rules_copy, catalog):
    """Normalisation is whitespace and NFC, and nothing else — a re-wrapped quote is the same
    quote, so this must not be a false positive."""

    def mutate(rows):
        row = next(r for r in rows if r["ziffer"] == "4")
        row["quote"] = "  " + row["quote"].replace(" ", "   ") + "  "

    _rewrite(rules_copy / "quantity_limits.manual.csv", mutate)
    _, v = _run(rules_copy, catalog)
    assert _failures(v, "citation_verbatim") == []


# ==============================================================================================
# Mengenbegrenzung — the unsupported-window gate
# ==============================================================================================


@pytest.mark.parametrize("window", ["sitzung", "behandlungstag", "kalenderjahr", "6_monate", ""])
def test_an_unsupported_window_is_an_error(rules_copy, catalog, window):
    """`build_fact_rows` emits quantity_limit without a window, so any value other than
    behandlungsfall would be enforced at the wrong width instead of being skipped."""
    _rewrite(
        rules_copy / "quantity_limits.manual.csv", lambda rows: rows[0].update({"window": window})
    )
    code, v = _run(rules_copy, catalog)
    assert code == 1
    assert _failures(v, "window_supported") or _failures(v, "required:window")


@pytest.mark.parametrize("bad", ["0", "-1"])
def test_a_non_positive_max_count_is_an_error(rules_copy, catalog, bad):
    _rewrite(
        rules_copy / "quantity_limits.manual.csv", lambda rows: rows[0].update({"max_count": bad})
    )
    code, v = _run(rules_copy, catalog)
    assert code == 1
    assert _failures(v, "max_count_positive")


def test_a_non_numeric_max_count_is_an_error(rules_copy, catalog):
    """The loader would coerce `int(row.get("max_count") or "1")` — actually raise — but a value
    like "einmal" must be caught here rather than at import time."""
    _rewrite(
        rules_copy / "quantity_limits.manual.csv",
        lambda rows: rows[0].update({"max_count": "einmal"}),
    )
    code, v = _run(rules_copy, catalog)
    assert code == 1
    assert _failures(v, "max_count_int")


# ==============================================================================================
# Geschlecht / Alter
# ==============================================================================================


@pytest.mark.parametrize("bad", ["f", "male", "W", "weiblich", "x"])
def test_an_out_of_vocabulary_gender_is_an_error(rules_copy, catalog, bad):
    _rewrite(
        rules_copy / "gender_restrictions.manual.csv",
        lambda rows: rows[0].update({"allowed_gender": bad}),
    )
    code, v = _run(rules_copy, catalog)
    assert code == 1
    assert _failures(v, "gender_vocabulary")


def test_an_inverted_age_band_is_an_error(rules_copy, catalog):
    def mutate(rows):
        rows[0]["min_age"] = "40"
        rows[0]["max_age"] = "13"

    _rewrite(rules_copy / "age_restrictions.manual.csv", mutate)
    code, v = _run(rules_copy, catalog)
    assert code == 1
    assert _failures(v, "age_band_coherent")


def test_an_age_row_with_no_bound_at_all_is_an_error(rules_copy, catalog):
    def mutate(rows):
        rows[0]["min_age"] = ""
        rows[0]["max_age"] = ""

    _rewrite(rules_copy / "age_restrictions.manual.csv", mutate)
    code, v = _run(rules_copy, catalog)
    assert code == 1
    assert _failures(v, "age_has_a_bound")


@pytest.mark.parametrize("bad", ["-1", "999", "131"])
def test_an_age_outside_the_patient_range_is_an_error(rules_copy, catalog, bad):
    _rewrite(rules_copy / "age_restrictions.manual.csv", lambda rows: rows[0].update({"max_age": bad}))
    code, v = _run(rules_copy, catalog)
    assert code == 1
    assert _failures(v, "max_age_in_range")


def test_shifting_a_vollendet_boundary_by_one_is_caught(rules_copy, catalog):
    """"bis zum vollendeten 8. Lebensjahr" is age <= 7. Encoding 8 is the classic off-by-one."""

    def mutate(rows):
        row = next(r for r in rows if r["ziffer"] == "250a")
        row["max_age"] = "8"

    _rewrite(rules_copy / "age_restrictions.manual.csv", mutate)
    _, v = _run(rules_copy, catalog)
    assert _failures(v, "vollendet_max_age")


def test_every_shipped_vollendet_boundary_is_encoded_correctly(catalog):
    """No shipped row may trip the off-by-one check."""
    _, v = _run(RULES_DIR, catalog)
    assert _failures(v, "vollendet_max_age") == []


# ==============================================================================================
# Zeitbeziehung
# ==============================================================================================


def _time_relation_row(**overrides) -> dict:
    row = {
        "rule_id": "tr_man_test",
        "ziffer_a": "4",
        "ziffer_b": "5",
        "relation": "same_day_excludes",
        "min_hours": "",
        "legal_basis": "GOÄ Anmerkung zu Nummer 4 und 5",
        "quote": "Die Leistung nach Nummer 4 ist im Behandlungsfall nur einmal berechnungsfähig.",
        "verified": "true",
        "verified_at": "2026-09-12",
        "source": "test",
    }
    row.update(overrides)
    return row


def _write_time_relations(rules_copy: Path, rows: list[dict]) -> None:
    spec = next(f for f in validator_module.FAMILIES if f.filename.startswith("time_relations"))
    with open(rules_copy / spec.filename, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(spec.columns))
        writer.writeheader()
        writer.writerows(rows)


def test_an_unknown_relation_is_an_error(rules_copy, catalog):
    _write_time_relations(rules_copy, [_time_relation_row(relation="within_14_days")])
    code, v = _run(rules_copy, catalog)
    assert code == 1
    assert _failures(v, "relation_vocabulary")


def test_a_self_referential_time_relation_is_an_error(rules_copy, catalog):
    _write_time_relations(rules_copy, [_time_relation_row(ziffer_a="4", ziffer_b="4")])
    code, v = _run(rules_copy, catalog)
    assert code == 1
    assert _failures(v, "distinct_ziffern")


def test_an_advisory_relation_is_flagged_but_not_an_error(rules_copy, catalog):
    """`min_hours_apart` is in the vocabulary and is never enforced. Shipping one is allowed;
    counting it as enforced coverage is what the WARN exists to prevent."""
    _write_time_relations(rules_copy, [_time_relation_row(relation="min_hours_apart", min_hours="1")])
    code, v = _run(rules_copy, catalog)
    assert code == 0
    assert _failures(v, "relation_is_enforced")


def test_min_hours_on_an_enforced_relation_is_flagged(rules_copy, catalog):
    """The fact tuple has no min_hours slot, so a threshold here would vanish silently."""
    _write_time_relations(
        rules_copy, [_time_relation_row(relation="same_day_excludes", min_hours="45")]
    )
    _, v = _run(rules_copy, catalog)
    assert _failures(v, "min_hours_not_enforced")


# ==============================================================================================
# CLI surface
# ==============================================================================================


def test_the_cli_exits_zero_on_the_shipped_corpus(capsys):
    assert validator_module.main(["--rules-dir", str(RULES_DIR)]) == 0


def test_the_cli_emits_parseable_json(capsys):
    validator_module.main(["--rules-dir", str(RULES_DIR), "--json", "--all"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["errors"] == 0
    assert sum(payload["row_counts"].values()) == 37
    assert payload["total_checks"] > 500


def test_the_cli_exits_one_when_a_row_is_broken(rules_copy, capsys):
    _rewrite(rules_copy / "quantity_limits.manual.csv", lambda rows: rows[0].update({"quote": ""}))
    assert validator_module.main(["--rules-dir", str(rules_copy)]) == 1


# ==============================================================================================
# The mutation harness (`scripts/mutate_batch2.py`)
# ==============================================================================================

_mut_spec = importlib.util.spec_from_file_location(
    "mutate_batch2", ENGINE_ROOT / "scripts" / "mutate_batch2.py"
)
mutation_module = importlib.util.module_from_spec(_mut_spec)
sys.modules["mutate_batch2"] = mutation_module
_mut_spec.loader.exec_module(mutation_module)


def test_every_mutation_declares_an_expectation():
    """A mutation with no predicted outcome cannot distinguish a survivor from a surprise."""
    assert mutation_module.MUTATIONS
    for m in mutation_module.MUTATIONS:
        assert m.expected in {"detected", "survives"}, m.id
        assert m.file in mutation_module.FILES, m.id
        assert m.description, m.id


def test_every_predicted_survivor_explains_itself():
    """A survivor without a reason is an unexamined hole, not a documented limitation."""
    for m in mutation_module.MUTATIONS:
        if m.expected == "survives":
            assert m.note, f"{m.id} is predicted to survive but says nothing about why"


def test_mutation_ids_are_unique():
    ids = [m.id for m in mutation_module.MUTATIONS]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize(
    "mutation_id", ["M08", "M15", "M16", "M22", "M23", "M01"]
)
def test_a_representative_mutation_is_detected(mutation_id):
    """One per detection class: unsupported window, invented citation, tidied citation,
    duplicate id, unknown Ziffer, shifted age boundary."""
    mutation = next(m for m in mutation_module.MUTATIONS if m.id == mutation_id)
    result = mutation_module.run_mutation(mutation, keep=False)
    assert result["detected"], result
    assert result["exit_code"] != 0
    assert result["caught_by"], "a detected mutation must name the check that caught it"


def test_a_predicted_survivor_really_does_survive():
    """M11 reverses GOÄ 27's allowed_gender to 'm'. Pinned as a known blind spot, so that if the
    validator ever learns to read the German it is a deliberate improvement, not a silent one."""
    mutation = next(m for m in mutation_module.MUTATIONS if m.id == "M11")
    result = mutation_module.run_mutation(mutation, keep=False)
    assert result["survivor"]
    assert result["result"] == "OK"


def test_the_harness_leaves_the_real_rule_files_untouched():
    """The isolation guarantee, asserted rather than assumed."""
    before = mutation_module._digests()
    for mutation_id in ("M03", "M26"):
        mutation = next(m for m in mutation_module.MUTATIONS if m.id == mutation_id)
        mutation_module.run_mutation(mutation, keep=False)
    assert mutation_module.verify_working_tree_is_clean(before)
