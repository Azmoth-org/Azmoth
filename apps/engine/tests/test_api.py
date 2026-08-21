"""The HTTP contract.

The POC's tests for its static `/manual` page, its `/deck` presentation and its experimental
free-text `POST /api/v1/code` endpoint are not here: none of those artefacts is part of this
monorepo (docs/migration/MIGRATION_PLAN.md §2). Everything else is, plus the contract the
production fixes added — a DRAFT proposal, a receipt hash and the rule-coverage counts.
"""

from __future__ import annotations

from tests.conftest import solve_payload, solve_proposal

# ------------------------------------------------------------------------------------------
# health and catalog
# ------------------------------------------------------------------------------------------


def test_health_reports_mode_engines_and_coverage(client):
    body = client.get("/api/v1/health").json()

    assert body["status"] == "ok"
    assert body["extraction_mode"] == "manual"
    assert body["catalog_version"].startswith("goae_official_snapshot_")
    assert body["rule_coverage"] == "partial"
    assert body["souffle_available"] is True
    assert body["souffle_version"].startswith("2.")
    assert body["clingo_version"]
    assert body["catalog_ziffern"] > 2000
    assert body["rules_enforced"] > 0
    assert body["unverified_rules_not_enforced"] > 0


def test_health_reports_the_solver_timeout_and_the_logic_version(client):
    """Both are part of what makes a result reproducible, so both are published."""
    body = client.get("/api/v1/health").json()

    assert body["solver_timeout_seconds"] > 0, "an unbounded solver must not be representable"
    assert len(body["logic_version"]) == 64, "sha256 over the .dl and .lp programs"


def test_catalog_publishes_provenance_and_warns_about_coverage(client):
    body = client.get("/api/v1/catalog").json()

    assert body["catalog_version"].startswith("goae_official_snapshot_")
    assert len(body["catalog_sha256"]) == 64
    assert "gesetze-im-internet.de" in body["source"]["url"]
    assert len(body["source"]["sha256_raw"]) == 64
    assert body["rule_coverage"] == "partial"
    assert body["ziffern"] > 2000
    assert body["imported_rules"]["exclusions_enforced"] > 0
    assert body["warnings"], "partial coverage must be stated, not implied"
    assert any("coverage" in w.lower() for w in body["warnings"])


def test_catalog_states_the_enforced_and_advisory_split(client):
    """The API must never imply that unverified rules are enforced."""
    coverage = client.get("/api/v1/catalog").json()["rule_coverage_detail"]

    assert coverage["enforced_rule_count"] > 0
    assert coverage["advisory_rule_count"] > 0
    assert coverage["suppressed_unverified_rule_count"] > 0
    assert coverage["policy_for_unverified_rules"] == "warn"


def test_catalog_does_not_dump_every_position(client):
    """2000-plus entries would make the provenance endpoint useless as a summary."""
    body = client.get("/api/v1/catalog").json()

    assert "ziffern" in body and isinstance(body["ziffern"], int)


def test_catalog_ziffer_lookup(client):
    body = client.get("/api/v1/catalog/ziffer/301").json()

    assert body["punkte"] == 160
    assert body["category"] == "C"
    assert body["official_text"].startswith("Punktion")
    assert body["factor_band"]["threshold"] == "2.3"
    assert body["provenance"] == "official"


def test_catalog_ziffer_lookup_reports_enforced_exclusions(client):
    body = client.get("/api/v1/catalog/ziffer/7").json()

    excluded = {e["excludes"] for e in body["exclusions_enforced"]}
    assert {"5", "6", "8"} <= excluded
    for entry in body["exclusions_enforced"]:
        assert entry["rule_id"]
        assert entry["legal_basis"]


def test_unknown_ziffer_is_404_with_a_clear_error(client):
    response = client.get("/api/v1/catalog/ziffer/99999")

    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "unknown_ziffer"


# ------------------------------------------------------------------------------------------
# solving
# ------------------------------------------------------------------------------------------


def test_solve_returns_a_draft_proposal(client, manual_case):
    body = solve_proposal(client, manual_case("case_001_knee"))

    assert body["status"] == "DRAFT", "the engine proposes; a human approves"
    assert body["proposal_id"].startswith("prop_")
    assert body["approved_at"] is None and body["approved_by"] is None
    assert len(body["receipt_hash"]) == 64
    assert body["catalog_version"].startswith("goae_official_snapshot_")
    assert body["rules_version"]
    assert body["solver_version"]


def test_solve_returns_the_documented_shape(client, manual_case):
    body = solve_payload(client, manual_case("case_001_knee"))

    assert set(body) == {"extraction", "coding", "audit_trail"}
    assert {
        "proposed_codes",
        "blocked_codes",
        "analog_codes",
        "warnings",
        "missing_documentation",
        "total",
    } <= set(body["coding"])


def test_proposed_code_has_every_documented_field(client, manual_case):
    body = solve_payload(client, manual_case("case_001_knee"))
    line = body["coding"]["proposed_codes"][0]

    for field in (
        "ziffer",
        "official_text",
        "punkte",
        "category",
        "factor",
        "justification_required",
        "justification_present",
        "confidence",
        "status",
        "proof",
        "amount_eur",
        "amount_cent_unrounded",
    ):
        assert field in line, f"proposed code is missing {field}"


def test_blocked_code_has_every_documented_field(client, manual_case):
    body = solve_payload(client, manual_case("case_001_knee"))
    blocked = body["coding"]["blocked_codes"][0]

    for field in (
        "ziffer",
        "official_text",
        "reason",
        "detail",
        "rule_id",
        "legal_basis",
        "reconciled_with_final_invoice",
    ):
        assert field in blocked, f"blocked code is missing {field}"


def test_warnings_have_a_type_and_message(client, manual_case):
    body = solve_payload(client, manual_case("case_001_knee"))

    assert body["coding"]["warnings"]
    for warning in body["coding"]["warnings"]:
        assert warning["type"]
        assert warning["message"]
        assert warning["severity"] in {"info", "warning", "error"}


def test_monetary_values_serialise_as_strings(client, manual_case):
    body = solve_payload(client, manual_case("case_001_knee"))

    assert isinstance(body["coding"]["total"]["amount_eur"], str)
    assert isinstance(body["coding"]["proposed_codes"][0]["factor"], str)


def test_setting_override_is_honoured(client, manual_case):
    payload = manual_case("case_001_knee")
    ambulant = solve_payload(client, payload)
    stationaer = solve_payload(client, payload, setting="stationaer")

    assert stationaer["coding"]["total"]["minderung_rate"] == "0.25"
    assert float(stationaer["coding"]["total"]["amount_eur"]) < float(
        ambulant["coding"]["total"]["amount_eur"]
    )


def test_a_schema_violation_is_422_not_a_wrong_invoice(client):
    response = client.post(
        "/api/v1/solve", json={"extraction": {"procedures": [{"typ": "punktion"}]}}
    )

    assert response.status_code == 422


def test_an_empty_extraction_produces_an_empty_invoice_not_an_error(client):
    response = client.post("/api/v1/solve", json={"extraction": {}})

    assert response.status_code == 200
    coding = response.json()["solver_result"]["coding"]
    assert coding["proposed_codes"] == []
    assert coding["total"]["amount_eur"] == "0.00"


def test_editing_the_extraction_changes_the_outcome_with_no_model_involved(client, manual_case):
    """The separation of the two halves, demonstrated over HTTP: remove the complete examination
    and the focused one stops losing its arbitration."""
    payload = manual_case("case_001_knee")
    with_both = solve_payload(client, payload)

    reduced = {**payload, "examinations": [
        e for e in payload["examinations"] if e["type"] == "symptombezogene_untersuchung"
    ]}
    only_focused = solve_payload(client, reduced)

    assert "7" in [line["ziffer"] for line in with_both["coding"]["proposed_codes"]]
    assert "5" not in [line["ziffer"] for line in with_both["coding"]["proposed_codes"]]

    charged = [line["ziffer"] for line in only_focused["coding"]["proposed_codes"]]
    assert "5" in charged and "7" not in charged
    assert only_focused["coding"]["conflicts_arbitrated"] == []


# ------------------------------------------------------------------------------------------
# nothing on this service needs a credential
# ------------------------------------------------------------------------------------------


def test_no_setting_holds_a_credential():
    """The acceptance criterion, asserted against the settings schema rather than one field name.

    The POC carried `OPENAI_API_KEY` for its experimental free-text path. That path is not part of
    this service, so there is no credential to leave empty — and this test fails if one reappears.
    """
    from app.config import Settings

    suspicious = [
        name
        for name in Settings.model_fields
        if any(token in name for token in ("key", "secret", "token", "password", "credential"))
    ]

    assert suspicious == [], f"the engine must not hold a credential: {suspicious}"


def test_every_endpoint_answers_without_authentication(client, manual_case):
    assert client.get("/api/v1/health").status_code == 200
    assert client.get("/api/v1/catalog").status_code == 200
    assert client.get("/api/v1/catalog/ziffer/7").status_code == 200
    assert client.get("/api/v1/vocabulary").status_code == 200
    assert (
        client.post("/api/v1/solve", json={"extraction": manual_case("case_001_knee")}).status_code
        == 200
    )


def test_the_dropped_poc_surfaces_are_really_gone(client):
    """A stale client hitting the POC's UI or LLM path must get a clean 404, not a half-answer."""
    for path in ("/", "/manual", "/deck", "/api/v1/manual_cases", "/api/v1/padnext/example"):
        assert client.get(path).status_code == 404, path
    assert client.post("/api/v1/code", json={"befund_text": "x"}).status_code == 404
    assert client.post("/api/v1/code/extract", json={"befund_text": "x"}).status_code == 404


def test_openapi_states_the_posture_the_service_actually_has(client):
    schema = client.get("/openapi.json").json()
    description = schema["info"]["description"]

    assert "DRAFT proposal, not an invoice" in description
    assert "Synthetic data only" in description
    assert "no model runs anywhere in this service" in description
    assert "/api/v1/code" not in schema["paths"], "the experimental LLM path was not migrated"


# ------------------------------------------------------------------------------------------
# the vocabulary that makes a form usable
# ------------------------------------------------------------------------------------------


def test_vocabulary_offers_every_mappable_entity_type(client):
    """A UI's pickers come from here. If a type the bridge can map were missing, the user would
    have no way to record that service; if one were present that the bridge cannot map, they could
    record something that is then silently not charged."""
    from app.bridge.entity_to_ziffer import load_mapping

    body = client.get("/api/v1/vocabulary").json()
    offered = {o["entity_type"] for options in body["entity_types"].values() for o in options}
    mappable = {row.entity_type for row in load_mapping()}

    assert mappable <= offered, f"not offered by the UI: {sorted(mappable - offered)}"


def test_vocabulary_includes_analog_only_types(client):
    """A service with no position of its own must still be recordable, or the § 6 Abs. 2 path is
    unreachable from the interface."""
    body = client.get("/api/v1/vocabulary").json()
    analog = [
        o for options in body["entity_types"].values() for o in options if o["analog_only"]
    ]

    assert analog, "no analog-only entity type is offered"
    assert any(o["entity_type"] == "optische_kohaerenztomographie" for o in analog)
    assert all(o["ziffern"] == [] for o in analog), "an analog-only type has no direct position"


def test_vocabulary_only_ever_names_positions_that_exist(client, catalog):
    body = client.get("/api/v1/vocabulary").json()

    for options in body["entity_types"].values():
        for option in options:
            for ziffer in option["ziffern"]:
                assert catalog.has(ziffer), f"{option['entity_type']} points at unknown {ziffer}"
            for organ in option["organs"]:
                for ziffer in organ["ziffern"]:
                    assert catalog.has(ziffer), f"{organ['value']} points at unknown {ziffer}"


def test_vocabulary_marks_when_an_organ_is_required(client):
    """A puncture without an organ maps to nothing, so a form must know to insist."""
    body = client.get("/api/v1/vocabulary").json()
    punktion = next(
        o for o in body["entity_types"]["procedure"] if o["entity_type"] == "punktion"
    )

    assert punktion["requires_organ"] is True
    assert {o["value"] for o in punktion["organs"]} >= {"knie", "schulter", "huefte"}


def test_vocabulary_shows_which_position_a_choice_leads_to(client):
    """The knee is the specificity demo: it can reach both Nr. 300 and the specific Nr. 301."""
    body = client.get("/api/v1/vocabulary").json()
    punktion = next(
        o for o in body["entity_types"]["procedure"] if o["entity_type"] == "punktion"
    )
    knie = next(o for o in punktion["organs"] if o["value"] == "knie")

    assert set(knie["ziffern"]) == {"300", "301"}


def test_vocabulary_carries_both_languages(client):
    body = client.get("/api/v1/vocabulary").json()

    for options in body["entity_types"].values():
        for option in options:
            assert option["label_de"], f"{option['entity_type']} has no German label"
            assert option["label_en"], f"{option['entity_type']} has no English label"
            assert option["label_de"] != option["entity_type"], (
                f"{option['entity_type']} label is just the identifier — unusable in a picker"
            )


def test_vocabulary_groups_types_by_where_they_belong(client):
    body = client.get("/api/v1/vocabulary").json()

    assert set(body["entity_types"]) <= {"consultation", "examination", "procedure", "lab_test"}
    assert body["counts"]["consultation"] >= 2
    assert body["counts"]["examination"] >= 3
    assert body["counts"]["procedure"] >= 10


def test_vocabulary_is_pinned_to_the_loaded_catalog(client):
    """So a stale cached vocabulary cannot be mistaken for the current one."""
    body = client.get("/api/v1/vocabulary").json()
    health = client.get("/api/v1/health").json()

    assert body["catalog_version"] == health["catalog_version"]


def test_every_offered_combination_actually_maps(client):
    """The point of the whole endpoint: anything a UI can offer must produce a candidate.

    This walks every (entity_type, organ) pair the picker exposes and checks the bridge maps it.
    A failure here means a form can lead a user into an `unmapped_entity` warning.
    """
    from app.bridge.entity_to_ziffer import map_extraction
    from app.catalog import load_catalog
    from app.config import RULES_DATA_DIR
    from app.rules.rule_store import RuleStore
    from app.schemas import ClinicalExtraction

    catalog, rules = load_catalog(), RuleStore.load(RULES_DATA_DIR)
    body = client.get("/api/v1/vocabulary").json()

    unmapped = []
    for kind, options in body["entity_types"].items():
        for option in options:
            if option["analog_only"]:
                continue
            organs = [o["value"] for o in option["organs"]] or [None]
            for organ in organs:
                entity = {"type": option["entity_type"]}
                if kind == "lab_test":
                    subtypes = [s["value"] for s in option["subtypes"]] or [option["entity_type"]]
                    payload = {"lab_tests": [{"type": subtypes[0]}]}
                elif kind == "examination":
                    payload = {"examinations": [{**entity, "organ_system": organ}]}
                elif kind == "consultation":
                    payload = {"consultation": entity}
                else:
                    # Use a complexity the type actually maps.
                    mapped = [c["value"] for c in option.get("complexities", [])]
                    if mapped:
                        entity["complexity"] = mapped[0]
                    payload = {"procedures": [{**entity, "organ": organ}]}

                bridge = map_extraction(
                    ClinicalExtraction.model_validate(payload), catalog, rules
                )
                if not bridge.candidates:
                    unmapped.append((option["entity_type"], organ))

    assert unmapped == [], f"the vocabulary offers combinations the bridge cannot map: {unmapped}"
