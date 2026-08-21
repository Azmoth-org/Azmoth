"""Both accepted request shapes for POST /api/v1/solve.

`curl -d @logic/tests/cases/case_001_knee/input.json` is the obvious thing to reach for, and the
case files are bare extractions, so the endpoint accepts either a bare extraction or the
`{"extraction": ...}` envelope. These tests pin both — and pin that tolerating the bare shape did
not weaken typo detection, which is the whole point of `extra="forbid"` on the input models.
"""

from __future__ import annotations

import json

from app.config import CASES_DIR
from app.core.canonical import canonical

#: Resolved from app.config rather than a CWD-relative literal, so the suite does not depend on
#: which directory pytest was invoked from.
CASE_PATH = CASES_DIR / "case_001_knee" / "input.json"


def load_case():
    return json.loads(CASE_PATH.read_text(encoding="utf-8"))


def test_case_file_is_a_bare_extraction():
    """The premise: if the fixture ever gained an envelope these tests would prove nothing."""
    payload = load_case()

    assert "extraction" not in payload
    assert "patient" in payload and "procedures" in payload


def test_solve_accepts_bare_extraction(client):
    resp = client.post("/api/v1/solve", json=load_case())

    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["status"] == "DRAFT"
    assert body["solver_result"]["coding"]["proposed_codes"]


def test_solve_accepts_wrapped_extraction(client):
    resp = client.post("/api/v1/solve", json={"extraction": load_case()})

    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["status"] == "DRAFT"
    assert body["solver_result"]["coding"]["proposed_codes"]


def test_bare_and_wrapped_extraction_produce_equivalent_output(client):
    extraction = load_case()

    bare = client.post("/api/v1/solve", json=extraction)
    wrapped = client.post("/api/v1/solve", json={"extraction": extraction})

    assert bare.status_code == 200
    assert wrapped.status_code == 200

    # `canonical` strips the proposal id, the timestamps and the measured timings — everything
    # that legitimately differs between two requests — and nothing else.
    assert canonical(bare.json()) == canonical(wrapped.json())
    assert bare.json()["receipt_hash"] == wrapped.json()["receipt_hash"]


def test_invalid_field_name_is_rejected_with_field_specific_error(client):
    """A typo must name the offending field.

    The bare-shape tolerance is keyed on "contains at least one extraction field" rather than
    "contains only extraction fields" precisely so that this stays true: a stricter rule would
    fail to wrap the body and then report every clinical field as unexpected, burying the typo.
    """
    bad_payload = {
        "procedures": [
            {
                "type": "sonographie",
                "orgna": "knie",
            }
        ]
    }

    resp = client.post("/api/v1/solve", json=bad_payload)

    assert resp.status_code == 422

    text = resp.text.lower()
    assert "orgna" in text
    assert "patient" not in text, (
        "the error should be about the typo'd field, not a list of every field that is missing"
    )


def test_typo_inside_the_envelope_is_also_field_specific(client):
    resp = client.post(
        "/api/v1/solve",
        json={"extraction": {"procedures": [{"type": "sonographie", "orgna": "knie"}]}},
    )

    assert resp.status_code == 422
    assert "orgna" in resp.text.lower()


def test_a_body_that_is_neither_shape_is_rejected(client):
    """No extraction field at all: must not be silently treated as an empty extraction."""
    resp = client.post("/api/v1/solve", json={"setting": "stationaer"})

    assert resp.status_code == 422
    assert "extraction" in resp.text


def test_setting_override_works_with_the_envelope(client):
    body = client.post(
        "/api/v1/solve",
        json={"extraction": load_case(), "setting": "stationaer"},
    ).json()
    total = body["solver_result"]["coding"]["total"]

    assert total["minderung_rate"] == "0.25"
    assert total["minderung_applied"] is True


def test_setting_can_still_be_expressed_inside_a_bare_extraction(client):
    """With no envelope there is nowhere to put `setting`, so patient.setting must carry it."""
    extraction = load_case()
    extraction["patient"]["setting"] = "belegarzt"

    body = client.post("/api/v1/solve", json=extraction).json()

    assert body["solver_result"]["coding"]["total"]["minderung_rate"] == "0.15"


def test_case_id_is_echoed_onto_the_proposal(client):
    """The caller's own identifier, so a proposal can be matched back to an encounter."""
    body = client.post(
        "/api/v1/solve", json={"extraction": load_case(), "case_id": "ENC-2026-0042"}
    ).json()

    assert body["case_id"] == "ENC-2026-0042"
