"""The frozen manual extraction contract, and the invariant that it stays free of billing."""

from __future__ import annotations

import json
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.core import extraction_prompts as prompts
from app.schemas import ClinicalExtraction

#: Fee-schedule concepts that must never appear anywhere in the extraction schema — not in a
#: field name, not in a description, not in a docstring. Pydantic copies docstrings and
#: descriptions into the JSON schema, and that schema is exactly what would be handed to a model
#: if extraction moved to structured outputs or tool calling.
#: `justification_factors` is a required field of the frozen input contract, and "factor" there
#: means "a contributing circumstance", not a multiplier. It is the one documented occurrence of
#: the substring, so it is masked out before the check rather than removed from the list — that
#: way a genuine `factor: 2.3` field would still fail, while the mandated field name passes.
#: Pydantic also emits a humanised title ("Justification Factors"), so the spaced form counts.
ALLOWED_FACTOR_IDENTIFIERS = (
    "justification_factors",
    "justification factors",
    "justificationfactor",
    "justification_factor",
)

FORBIDDEN_SCHEMA_TERMS = (
    "ziffer",
    "goae",
    "goä",
    "goez",
    "billing_code",
    "invoice",
    "steigerungsfaktor",
    "factor",
    "price",
    "amount",
    "punkte",
    "punktzahl",
    "punktwert",
    "gebühr",
    "gebuehr",
    "honorar",
    "schwellenwert",
    "hoechstsatz",
    "einfachsatz",
    "minderung",
    "analogansatz",
    "zielleistung",
)


def _mask_allowed(blob: str) -> str:
    for identifier in ALLOWED_FACTOR_IDENTIFIERS:
        blob = blob.replace(identifier, "justification_circumstances")
    return blob


def test_extraction_schema_has_no_billing_fields():
    schema = _mask_allowed(
        json.dumps(ClinicalExtraction.model_json_schema(), ensure_ascii=False).lower()
    )
    leaked = [term for term in FORBIDDEN_SCHEMA_TERMS if term in schema]

    assert leaked == [], (
        f"The extraction schema exposes fee-schedule concepts {leaked}. Clinical entities in, "
        "billing decisions out — the schema is the contract that keeps them apart."
    )


def test_extraction_schema_exposes_no_multiplier_semantics():
    """The point behind banning "factor": nothing in the input schema may carry a multiplier.

    `justification_factors` is allowed to exist, but neither it nor any other field may offer a
    numeric multiplier, a threshold or a ceiling — choosing those is § 5 GOÄ work, and it happens
    downstream where it can be checked against the law.
    """
    schema = ClinicalExtraction.model_json_schema()
    blob = json.dumps(schema, ensure_ascii=False).lower()

    for term in ("multiplier", "1.15", "2.3", "3.5", "threshold", "ceiling", "max_factor"):
        assert term not in blob, f"the input schema hints at a multiplier via {term!r}"

    circumstance = schema["$defs"]["JustificationFactor"]["properties"]
    assert set(circumstance) == {"id", "confidence", "reason", "severity", "applies_to"}, (
        "JustificationFactor gained a field; check it carries no multiplier"
    )


def test_openapi_extraction_component_has_no_billing_fields():
    """Same invariant, checked on the shape actually published to clients."""
    from app.main import app

    components = app.openapi()["components"]["schemas"]
    extraction_like = {
        name: body
        for name, body in components.items()
        if name
        in {
            "ClinicalExtraction",
            "Patient",
            "Consultation",
            "Examination",
            "Procedure",
            "LabTest",
            "Diagnosis",
            "JustificationFactor",
        }
    }
    assert extraction_like, "the extraction models are missing from the OpenAPI components"

    blob = _mask_allowed(json.dumps(extraction_like, ensure_ascii=False).lower())
    leaked = [term for term in FORBIDDEN_SCHEMA_TERMS if term in blob]
    assert leaked == [], f"billing concepts leaked into the published extraction schema: {leaked}"


# ------------------------------------------------------------------------------------------
# validation behaviour
# ------------------------------------------------------------------------------------------


def test_minimal_extraction_is_valid():
    extraction = ClinicalExtraction.model_validate({"patient": {"setting": "ambulant"}})

    assert extraction.patient.setting == "ambulant"
    assert extraction.examinations == []


def test_confidence_defaults_to_one_for_manual_input():
    extraction = ClinicalExtraction.model_validate(
        {"procedures": [{"type": "punktion", "organ": "knie"}]}
    )

    assert extraction.procedures[0].confidence == Decimal("1.0")


@pytest.mark.parametrize("bad", ["1.5", "-0.1", "2"])
def test_confidence_outside_zero_to_one_is_rejected(bad):
    with pytest.raises(ValidationError, match="between 0.0 and 1.0"):
        ClinicalExtraction.model_validate(
            {"procedures": [{"type": "punktion", "confidence": bad}]}
        )


def test_confidence_is_decimal_not_float():
    extraction = ClinicalExtraction.model_validate(
        {"procedures": [{"type": "punktion", "confidence": "0.7"}]}
    )

    assert isinstance(extraction.procedures[0].confidence, Decimal)
    assert extraction.procedures[0].confidence == Decimal("0.7")


@pytest.mark.parametrize("setting", ["ambulant", "stationaer", "belegarzt"])
def test_allowed_settings(setting):
    assert ClinicalExtraction.model_validate({"patient": {"setting": setting}})


def test_unknown_setting_is_rejected():
    with pytest.raises(ValidationError):
        ClinicalExtraction.model_validate({"patient": {"setting": "teilstationaer"}})


@pytest.mark.parametrize("severity", ["leicht", "mittel", "schwer"])
def test_allowed_severities(severity):
    extraction = ClinicalExtraction.model_validate(
        {"justification_factors": [{"reason": "x", "severity": severity}]}
    )
    assert extraction.justification_factors[0].severity == severity


def test_unknown_severity_is_rejected():
    with pytest.raises(ValidationError):
        ClinicalExtraction.model_validate(
            {"justification_factors": [{"reason": "x", "severity": "extrem"}]}
        )


def test_unknown_fields_are_rejected_rather_than_ignored():
    """A typo in hand-written JSON must be an error, not a silently dropped service."""
    with pytest.raises(ValidationError, match="extra_forbidden"):
        ClinicalExtraction.model_validate(
            {"procedures": [{"type": "punktion", "orgna": "knie"}]}
        )


def test_entity_ids_are_assigned_when_omitted():
    extraction = ClinicalExtraction.model_validate(
        {
            "consultation": {"type": "beratung"},
            "procedures": [{"type": "punktion"}, {"type": "sonographie"}],
            "lab_tests": [{"type": "crp"}],
        }
    )

    assert extraction.consultation.id == "consultation"
    assert [p.id for p in extraction.procedures] == ["proc_1", "proc_2"]
    assert [lab.id for lab in extraction.lab_tests] == ["lab_1"]


def test_explicit_entity_ids_are_preserved():
    extraction = ClinicalExtraction.model_validate(
        {"procedures": [{"id": "the_puncture", "type": "punktion"}]}
    )

    assert extraction.procedures[0].id == "the_puncture"
    assert "the_puncture" in extraction.entity_ids()


def test_applies_to_accepts_a_bare_string():
    """Writing one target by hand is the common case; dropping it would lose a justification."""
    extraction = ClinicalExtraction.model_validate(
        {"justification_factors": [{"reason": "x", "severity": "mittel", "applies_to": "punktion"}]}
    )

    assert extraction.justification_factors[0].applies_to == ["punktion"]


def test_applies_to_defaults_to_encounter_wide():
    extraction = ClinicalExtraction.model_validate(
        {"justification_factors": [{"reason": "x", "severity": "mittel"}]}
    )

    assert extraction.justification_factors[0].applies_to == []


def test_average_confidence_is_decimal():
    extraction = ClinicalExtraction.model_validate(
        {
            "procedures": [
                {"type": "a", "confidence": "0.5"},
                {"type": "b", "confidence": "1.0"},
            ]
        }
    )

    assert extraction.average_confidence() == Decimal("0.7500")


def test_decimals_serialise_as_strings_so_no_precision_is_lost():
    extraction = ClinicalExtraction.model_validate(
        {"procedures": [{"type": "punktion", "confidence": "0.70"}]}
    )
    dumped = extraction.model_dump(mode="json")

    assert dumped["procedures"][0]["confidence"] == "0.70"
    assert isinstance(dumped["procedures"][0]["confidence"], str)


# ------------------------------------------------------------------------------------------
# the experimental prompt is held to the same invariant
# ------------------------------------------------------------------------------------------


@pytest.mark.parametrize("term", prompts.FORBIDDEN_PROMPT_TERMS)
def test_experimental_prompt_contains_no_fee_schedule_vocabulary(term):
    """The LLM path is off by default, but if it is switched on the model still must not be
    told about the fee schedule. `FORBIDDEN_PROMPT_TERMS` would be a decorative constant if
    nothing checked it."""
    blob = (prompts.EXTRACTION_SYSTEM_PROMPT + "\n" + prompts.EXTRACTION_USER_PROMPT).lower()

    assert term not in blob, f"the extraction prompt mentions '{term}'"


def test_experimental_prompt_contains_no_catalog_ziffern(catalog):
    """Only multi-digit positions are checked: single digits appear legitimately as list
    numbering and in confidence ranges, so they cannot be told apart from a code."""
    blob = (prompts.EXTRACTION_SYSTEM_PROMPT + "\n" + prompts.EXTRACTION_USER_PROMPT).lower()
    leaked = [z for z in catalog.ziffern if len(z) >= 3 and z in blob]

    assert leaked == [], f"catalog Ziffern leaked into the prompt: {leaked}"


def test_experimental_prompt_documents_the_current_schema():
    """A prompt describing a schema the code no longer accepts produces rejected extractions."""
    system = prompts.EXTRACTION_SYSTEM_PROMPT

    assert '"applies_to": [string]' in system, "applies_to is a list now"
    assert "untersuchung_ganzkoerperstatus" in system
    assert "untersuchung_mehrere_organsysteme" not in system, "renamed; would not map"


def test_prompt_vocabulary_is_actually_mapped(catalog, rules):
    """Entity types the prompt suggests should either map to a position or be a documented
    analog case — otherwise the prompt is steering a model toward dead ends."""
    from app.bridge.entity_to_ziffer import load_mapping, normalize_key

    mapped = {r.entity_type for r in load_mapping()}
    analog = {normalize_key(r.source_entity_type) for r in rules.analog_candidates}

    suggested = {
        "punktion", "sonographie", "echokardiographie", "ekg", "ekg_rhythmusfeststellung",
        "langzeit_ekg", "roentgen", "verband", "dermatoskopie", "exzision_hautgeschwulst",
        "histologische_untersuchung", "optische_kohaerenztomographie",
        "symptombezogene_untersuchung", "vollstaendige_untersuchung_organsystem",
        "untersuchung_ganzkoerperstatus", "beratung", "eingehende_beratung",
    }
    unknown = sorted(suggested - mapped - analog)

    assert unknown == [], f"the prompt suggests entity types nothing handles: {unknown}"
