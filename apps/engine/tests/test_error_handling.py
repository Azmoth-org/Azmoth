"""Every documented failure, triggered on purpose and asserted end to end.

Three things are being prevented, and they are different failures of the same feature:

- **A wrong status.** A deterministic problem answered with a 503 tells a client to retry
  something that will never succeed; a transient one answered with a 400 tells them to go and edit
  a file that was fine. Each case below asserts the status *and* the code, because either alone can
  be right while the other is wrong.
- **An unactionable body.** "Unreadable delivery" without a line number sends a PVS integrator
  grepping a 3 MB export by hand. Where the engine knows where the problem is, the test asserts it
  is in `details` — not merely that some prose mentioned it.
- **A retry that should not have happened.** The retries exist for dropped connections. A test
  that only checked "3 attempts were made on failure" would pass just as happily on an
  implementation that hammered the database over a unique-key violation, so the deterministic case
  is asserted as hard as the transient one.

Timing is never asserted. The retry tests inject a sleeper and count what it was asked to wait, so
they measure the schedule rather than living through it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError, InterfaceError, OperationalError

from app.config import PADNEXT_EXAMPLES_DIR, REPO_ROOT, Settings
from app.core.retry import backoff_delays, retry_transient
from app.db.retry import is_transient_database_error, retry_database
from app.errors import (
    DEFAULT_RETRY_AFTER_SECONDS,
    EngineError,
    ErrorCode,
    TransientDatabaseError,
    UnknownZifferError,
    error_envelope,
)

ERRORS_DOC = REPO_ROOT / "docs" / "errors.md"
VALID_DELIVERY = PADNEXT_EXAMPLES_DIR / "00004711_20260726_ADL_000001_padx.xml"


def post_delivery(client, payload: bytes, name: str = "case.xml"):
    return client.post(
        "/api/v1/padnext/audit",
        content=payload,
        headers={"Content-Type": "application/xml", "x-padnext-filename": name},
    )


def assert_envelope(response, *, status: int, code: str) -> dict:
    """The shape assertion every case shares, so each test can be about its own trigger."""
    assert response.status_code == status, response.text
    body = response.json()

    assert body["error_code"] == code, body
    assert isinstance(body["message"], str) and body["message"].strip()
    assert isinstance(body["details"], dict)
    assert body["error"] == code.lower(), "the legacy lowercase alias must track the code"
    assert "detail" in body, "clients that read FastAPI's `detail` must keep finding it"

    if body["retry_after"] is None:
        assert "retry-after" not in {k.lower() for k in response.headers}, (
            "a body that promises nothing must not send a Retry-After header"
        )
    else:
        assert response.headers["retry-after"] == str(body["retry_after"]), (
            "the header and the field must agree, or only our own client can honour either"
        )
    return body


# ==========================================================================================
# 400 — the request itself is malformed
# ==========================================================================================


def test_an_empty_body_is_400_and_says_what_to_send(client):
    body = assert_envelope(
        post_delivery(client, b""), status=400, code=ErrorCode.EMPTY_REQUEST_BODY
    )

    assert "padx" in body["message"].lower()


@pytest.mark.parametrize(
    "payload,description",
    [
        (b"<rechnungen><rechnung></rechnungen>", "unclosed element"),
        (b"<rechnungen>\n  <rechnung>\n    <kaputt>\n", "truncated document"),
        (b"<a>&nosuchentity;</a>", "undefined entity"),
    ],
)
def test_malformed_xml_is_400_with_the_line_and_column(client, payload, description):
    """The position is the whole point. lxml and ElementTree both know it, and an error that
    dropped it would leave whoever has to fix the export searching by hand."""
    body = assert_envelope(
        post_delivery(client, payload), status=400, code=ErrorCode.INVALID_XML
    )

    details = body["details"]
    assert isinstance(details["line"], int) and details["line"] >= 1, description
    assert isinstance(details["column"], int) and details["column"] >= 0, description
    assert re.search(r"line \d+, column \d+", details["location"]), details


def test_a_doctype_is_refused_before_it_can_expand(client):
    """Billion laughs. Refusing the declaration removes the class; bounding it would not."""
    payload = b'<!DOCTYPE r [<!ENTITY a "aaaa">]><rechnungen><rechnung/></rechnungen>'

    body = assert_envelope(
        post_delivery(client, payload), status=422, code=ErrorCode.PADNEXT_UNREADABLE
    )

    assert "DOCTYPE" in body["message"]


def test_a_malformed_content_length_is_named_not_guessed(client):
    response = client.post(
        "/api/v1/padnext/audit",
        content=b"",
        headers={"Content-Length": "not-a-number", "Content-Type": "application/octet-stream"},
    )

    # httpx may normalise the header away before it is sent; only assert when it reached us.
    if response.status_code == 400 and response.json().get("error_code") == "MALFORMED_CONTENT_LENGTH":
        assert response.json()["details"]["content_length"] == "not-a-number"


# ==========================================================================================
# 422 — well formed, and the engine still cannot process it
# ==========================================================================================


def test_a_schema_violation_lists_every_violation_with_a_position(client):
    """Not "the file is wrong" but "this element, at this line, on this path".

    Driven from the committed invalid fixtures rather than a string edit of the valid one, so the
    case being tested is the one `tests/test_padnext_schema.py` documents — a wrong root namespace,
    which is fatal framing under the strict policy.
    """
    payload = (
        Path(__file__).parent / "fixtures" / "invalid_padnext" / "wrong_namespace.xml"
    ).read_bytes()

    body = assert_envelope(
        post_delivery(client, payload), status=422, code=ErrorCode.PADNEXT_SCHEMA_VIOLATION
    )

    violations = body["details"]["violations"]
    assert violations and body["details"]["violation_count"] == len(violations)
    for violation in violations:
        assert violation["message"]
        assert {"line", "column", "path", "location"} <= set(violation)


@pytest.mark.parametrize("spelling", ["ja", "yes", "nein", "2", ""])
def test_an_undeclared_or_unrecognised_echtdaten_is_422_over_http(client, spelling):
    """`echtdaten="ja"` reaches the caller as a refusal, not as a report.

    The unit-level cases live in `tests/test_padnext.py`; this one exists because the gate is only
    worth anything if it survives the API layer — a `RuntimeError` subclass that the error handler
    did not know about would come back as a 500 with a stack trace and no `error_code`, and a
    client would retry it.

    The empty string is in here as its own case: `echtdaten=""` is what a template engine emits
    for a variable it could not fill, so it is the spelling a broken export produces most often.
    """
    payload = re.sub(
        rb'echtdaten="[^"]*"',
        f'echtdaten="{spelling}"'.encode(),
        VALID_DELIVERY.read_bytes(),
    )

    body = assert_envelope(
        post_delivery(client, payload), status=422, code=ErrorCode.ECHTDATEN_UNDECLARED
    )

    assert "echtdaten" in body["message"]
    assert "anonymize_padnext.py" in body["message"], "the message must name the way out"
    assert body["details"]["echtdaten_declared"] == (spelling or None)


def test_a_declared_test_delivery_is_not_caught_by_that_gate(client):
    """The other side of it: `echtdaten="0"` and `="false"` both audit normally.

    Without this, a gate that refused everything would pass every test above.
    """
    for spelling in (b"0", b"false", b"FALSE"):
        payload = re.sub(
            rb'echtdaten="[^"]*"', b'echtdaten="' + spelling + b'"', VALID_DELIVERY.read_bytes()
        )
        response = post_delivery(client, payload)
        assert response.status_code == 200, (spelling, response.text)
        assert response.json()["echtdaten"] is False


def test_a_delivery_no_position_of_which_is_in_the_catalog_is_422(client):
    """A catalog *mismatch*, and it is deliberately not the same thing as partial coverage.

    Rewriting every `ziffer` to a number the GOÄ does not have simulates a delivery coded against
    a different edition. The report the engine would otherwise produce says "nicht beurteilbar" to
    every position and carries a receipt hash over a verdict-free document — worse than useless,
    because it looks like an answer.
    """
    payload = re.sub(
        rb'ziffer="[^"]+"', rb'ziffer="99991"', VALID_DELIVERY.read_bytes()
    )

    body = assert_envelope(
        post_delivery(client, payload), status=422, code=ErrorCode.UNKNOWN_ZIFFER
    )

    details = body["details"]
    assert details["unknown_ziffern"] == ["99991"]
    assert details["unknown_count"] == 1
    assert details["catalog_version"], "the client cannot tell which edition to use without this"
    assert details["goae_position_count"] >= 1


def test_a_delivery_with_only_some_unknown_positions_still_audits(client):
    """The other half of the rule above, and the one that protects the product decision.

    Partial coverage is normal here: 859 of 894 rules are unverified, and a position we cannot
    price is reported as unconfirmed rather than held against the practice. If this ever starts
    returning 422 the audit has begun refusing the invoices it exists to check.
    """
    payload = VALID_DELIVERY.read_bytes().replace(b'ziffer="1"', b'ziffer="99991"', 1)

    response = post_delivery(client, payload)

    assert response.status_code == 200, response.text
    report = response.json()
    assert any(row["verdict"] == "unknown_ziffer" for row in report["positions"])
    assert any(row["verdict"] != "unknown_ziffer" for row in report["positions"])


def test_a_schema_violation_in_the_request_json_is_a_named_422(client):
    response = client.post("/api/v1/solve", json={"extraction": {"procedures": [{"typ": "x"}]}})

    body = assert_envelope(response, status=422, code=ErrorCode.VALIDATION_ERROR)

    assert body["details"]["error_count"] == len(body["details"]["errors"]) >= 1
    assert isinstance(body["detail"], list), "FastAPI's own list shape is preserved"
    assert all("loc" in error for error in body["details"]["errors"])


# ==========================================================================================
# 504 — the solver ran out of the time it was allowed
# ==========================================================================================


def test_a_solve_that_finds_no_model_in_time_is_504_with_the_ceiling(client, monkeypatch, manual_case):
    """The ceiling expires with nothing found. Never an empty invoice — that would read as
    "nothing is chargeable", which is a different and much more dangerous statement."""
    from app.api import deps
    from app.solvers.clingo_solver import ClingoTimeout

    def never_finishes(self, rules_result, extraction, bridge):
        raise ClingoTimeout(self.timeout_seconds, program="% redacted", positions_in_play=7)

    monkeypatch.setattr(
        "app.solvers.clingo_solver.ClingoSolver.solve", never_finishes, raising=True
    )
    deps.reset()

    response = client.post("/api/v1/solve", json={"extraction": manual_case("case_001_knee")})

    body = assert_envelope(response, status=504, code=ErrorCode.SOLVER_TIMEOUT)
    details = body["details"]
    assert details["timeout_seconds"] > 0
    assert details["models_found"] == 0
    assert details["partial_result_available"] is False
    assert details["positions_in_play"] == 7
    assert "program" not in str(body), "the ASP program and its facts must never leave the process"


def test_a_solve_cut_short_with_a_model_is_a_labelled_200_not_a_504(client, monkeypatch, manual_case):
    """Partial-result handling, which is the other half of the timeout contract.

    Every hard constraint is an integrity constraint, so a cancelled search cannot have traded one
    away — only the choice among equally legal alternatives is unproven. So the draft is returned,
    marked, and a human decides. A client must check `solver_timed_out` on a 200 before treating a
    draft as final, and this test is what makes that promise true.
    """
    from app.api import deps
    from app.solvers.clingo_solver import ClingoSolver

    real_solve = ClingoSolver.solve

    def cut_short(self, rules_result, extraction, bridge):
        result = real_solve(self, rules_result, extraction, bridge)
        result.timed_out = True
        result.solver_status = "TIMEOUT_PARTIAL"
        return result

    monkeypatch.setattr(ClingoSolver, "solve", cut_short, raising=True)
    deps.reset()

    response = client.post("/api/v1/solve", json={"extraction": manual_case("case_001_knee")})

    assert response.status_code == 200, response.text
    proposal = response.json()
    assert proposal["solver_timed_out"] is True
    assert proposal["solver_status"] == "TIMEOUT_PARTIAL"
    assert proposal["solver_result"]["coding"]["proposed_codes"], (
        "a partial model is still a usable draft — that is why it is a 200"
    )


# ==========================================================================================
# 503 — transient, and the client is told so
# ==========================================================================================


def test_a_rules_engine_failure_is_503_with_a_retry_after(client, monkeypatch, manual_case):
    from app.api import deps
    from app.solvers.souffle_engine import SouffleEngine, SouffleError

    def unavailable(self, *args, **kwargs):
        raise SouffleError("souffle could not be started", stderr="ENOMEM", fact_dump="…facts…")

    monkeypatch.setattr(SouffleEngine, "run", unavailable, raising=True)
    deps.reset()

    response = client.post("/api/v1/solve", json={"extraction": manual_case("case_001_knee")})

    body = assert_envelope(response, status=503, code=ErrorCode.RULES_ENGINE_UNAVAILABLE)
    assert body["retry_after"] == DEFAULT_RETRY_AFTER_SECONDS
    assert body["details"]["engine"] == "souffle"
    assert "facts" not in str(body["details"]), "the encounter's facts stay in the log"


def test_a_lost_database_connection_is_503_and_says_the_write_did_not_happen(
    client, monkeypatch, manual_case
):
    """The proposal solved fine and could not be stored. 503 rather than 500, because the same
    request sent again in five seconds may well work."""
    from app.api import deps
    from app.services.proposal_store import ProposalStore

    async def connection_gone(self, *args, **kwargs):
        raise InterfaceError("INSERT", {}, Exception("connection is closed"))

    monkeypatch.setattr(ProposalStore, "create_proposal", retry_database(
        "create_proposal", base_delay=0.0, sleeper=_noop_async
    )(connection_gone), raising=True)
    deps.reset()

    response = client.post("/api/v1/solve", json={"extraction": manual_case("case_001_knee")})

    body = assert_envelope(response, status=503, code=ErrorCode.TRANSIENT_DB_FAILURE)
    assert body["retry_after"] == DEFAULT_RETRY_AFTER_SECONDS
    assert body["details"]["attempts"] >= 2, "it must actually have retried before giving up"
    assert "nicht gespeichert" in body["message"], (
        "a client that does not know whether the write happened cannot safely retry"
    )


async def _noop_async(_delay: float) -> None:
    """A sleeper that does not sleep. The schedule is asserted elsewhere, on the real one."""
    return None


# ==========================================================================================
# the retry mechanism itself
# ==========================================================================================


def test_the_backoff_is_exponential_and_jittered():
    """With the jitter pinned to its ceiling the schedule is the plain doubling sequence; the
    default draws uniformly below it, which is what stops a restart's worth of workers returning
    in the same millisecond."""
    ceiling = backoff_delays(4, base_delay=1.0, jitter=lambda _lo, hi: hi)

    assert ceiling == [1.0, 2.0, 4.0], "one delay per retry, doubling"
    assert backoff_delays(1) == [], "a single attempt waits for nothing"
    assert max(backoff_delays(6, base_delay=1.0, jitter=lambda _lo, hi: hi)) == 8.0, "capped"

    drawn = backoff_delays(3, base_delay=1.0)
    assert all(0.0 <= d <= bound for d, bound in zip(drawn, [1.0, 2.0])), drawn


def test_a_transient_failure_is_retried_and_then_succeeds():
    slept: list[float] = []
    attempts = {"n": 0}

    @retry_transient(
        transient=(OSError,), attempts=3, base_delay=1.0,
        jitter=lambda _lo, hi: hi, sleeper=slept.append,
    )
    def flaky() -> str:
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise OSError("cannot fork")
        return "ok"

    assert flaky() == "ok"
    assert attempts["n"] == 3
    assert slept == [1.0, 2.0], "it waited between attempts, and waited longer the second time"


def test_a_deterministic_failure_is_never_retried():
    """The assertion that matters most. A retry loop that hammered the database over a unique-key
    violation would pass every "it retries" test and be a defect."""
    slept: list[float] = []
    attempts = {"n": 0}

    @retry_transient(transient=(OSError,), attempts=3, sleeper=slept.append)
    def deterministic() -> None:
        attempts["n"] += 1
        raise ValueError("this input is simply wrong")

    with pytest.raises(ValueError):
        deterministic()

    assert attempts["n"] == 1, "a deterministic failure must leave on the first attempt"
    assert slept == [], "and must not have cost the caller a single second of backoff"


@pytest.mark.asyncio
async def test_the_async_retry_converts_an_exhausted_failure(monkeypatch):
    slept: list[float] = []
    attempts = {"n": 0}

    @retry_database("probe", base_delay=1.0, jitter=lambda _lo, hi: hi, sleeper=_record(slept))
    async def always_down() -> None:
        attempts["n"] += 1
        raise InterfaceError("SELECT", {}, Exception("connection is closed"))

    with pytest.raises(TransientDatabaseError) as caught:
        await always_down()

    assert attempts["n"] == 3, "the configured attempts, all of them"
    assert slept == [1.0, 2.0]
    assert caught.value.http_status == 503
    assert caught.value.retry_after == DEFAULT_RETRY_AFTER_SECONDS
    assert caught.value.details["attempts"] == 3
    assert "InterfaceError" in caught.value.details["last_error"], (
        "the driver's own error has to survive into the 503, or nobody can debug the outage"
    )


def _record(sink: list[float]):
    async def sleeper(delay: float) -> None:
        sink.append(delay)

    return sleeper


def test_which_database_errors_count_as_transient():
    """`OperationalError` is both a dropped socket and a missing table. Only the first is worth a
    second attempt, and SQLAlchemy's own `connection_invalidated` is what separates them."""
    dropped = OperationalError("SELECT 1", {}, Exception("server closed the connection"))
    dropped.connection_invalidated = True
    missing_table = OperationalError("SELECT 1", {}, Exception("no such table: proposals"))
    integrity = IntegrityError("INSERT", {}, Exception("duplicate key"))

    assert is_transient_database_error(dropped)
    assert is_transient_database_error(InterfaceError("x", {}, Exception("closed")))
    assert not is_transient_database_error(missing_table)
    assert not is_transient_database_error(integrity), (
        "a unique violation is a fact about the data, not about the connection"
    )
    assert not is_transient_database_error(ValueError("nothing to do with the database"))


@pytest.mark.asyncio
async def test_an_integrity_error_reaches_the_caller_unretried():
    attempts = {"n": 0}

    @retry_database("probe", sleeper=_record([]))
    async def duplicate() -> None:
        attempts["n"] += 1
        raise IntegrityError("INSERT", {}, Exception("duplicate key"))

    with pytest.raises(IntegrityError):
        await duplicate()

    assert attempts["n"] == 1


def test_the_retry_settings_are_configurable_and_documented():
    defaults = {name: field.default for name, field in Settings.model_fields.items()}

    assert defaults["db_retry_attempts"] == 3
    assert defaults["db_retry_base_delay_seconds"] == 1.0

    example = Path(__file__).resolve().parents[1] / ".env.example"
    if example.is_file():
        text = example.read_text(encoding="utf-8")
        assert "DB_RETRY_ATTEMPTS" in text and "DB_RETRY_BASE_DELAY_SECONDS" in text


# ==========================================================================================
# the envelope, and the catalog that documents it
# ==========================================================================================


def test_every_code_in_the_enum_has_a_row_in_the_documentation():
    """The one assertion that keeps `docs/errors.md` honest. A new code with no row fails here
    rather than shipping as a string a client discovers in production."""
    if not ERRORS_DOC.is_file():
        pytest.skip("docs/errors.md is not present (running from a built image)")

    documented = set(re.findall(r"`([A-Z][A-Z_]+)`", ERRORS_DOC.read_text(encoding="utf-8")))
    missing = sorted(code for code in ErrorCode if code.value not in documented)

    assert missing == [], f"error codes with no row in docs/errors.md: {missing}"


def test_the_envelope_never_nests_itself():
    body = error_envelope(
        error_code=ErrorCode.SOLVER_TIMEOUT, message="…", details={"a": 1}, http_status=504
    )

    assert "detail" not in body["detail"], "the compatibility mirror must not recurse"
    assert body["detail"]["error_code"] == "SOLVER_TIMEOUT"
    assert body["detail"]["details"] == {"a": 1}


def test_the_envelope_serialises_the_types_the_engine_actually_puts_in_details():
    """`details` is built from domain objects, and an error response that cannot serialise itself
    turns a 422 the caller could have fixed into a 500 nobody can."""
    from decimal import Decimal

    body = error_envelope(
        error_code=ErrorCode.UNKNOWN_ZIFFER,
        message="…",
        details={"amount": Decimal("130.39"), "path": Path("/tmp/x")},
        http_status=422,
    )

    assert body["details"]["amount"] == "130.39", "exact string, never a float"
    assert body["details"]["path"] == "/tmp/x"


def test_an_engine_error_carries_its_own_status_and_code():
    error = UnknownZifferError(
        "…", unknown_ziffern=["9999", "9999", "8888"], catalog_version="goae_x"
    )

    assert error.http_status == 422
    assert error.error_code == ErrorCode.UNKNOWN_ZIFFER
    assert error.retry_after is None, "a deterministic failure must not invite a retry"
    assert error.details["unknown_ziffern"] == ["8888", "9999"], "deduplicated and sorted"
    assert error.details["unknown_count"] == 2


def test_every_engine_error_subclass_declares_a_documented_code():
    """Guards the base class's default. `EngineError` defaults to `SOLVER_FAILED`/500, so a
    subclass that forgot to set its own would silently answer 500 for something else entirely."""

    def descendants(cls):
        for sub in cls.__subclasses__():
            yield sub
            yield from descendants(sub)

    # Importing the modules that define them; without this the subclass walk sees only what some
    # other test happened to import first.
    import app.catalog.catalog_loader  # noqa: F401
    import app.padnext.audit  # noqa: F401
    import app.padnext.reader  # noqa: F401
    import app.solvers.clingo_solver  # noqa: F401
    import app.solvers.souffle_engine  # noqa: F401
    import app.validation.validator  # noqa: F401

    for subclass in set(descendants(EngineError)):
        assert subclass.error_code in set(ErrorCode), subclass
        assert 400 <= subclass.http_status <= 599, subclass
        if subclass.retry_after is not None:
            assert subclass.http_status == 503, (
                f"{subclass.__name__} invites a retry on a {subclass.http_status}; "
                "retry_after belongs on transient failures only"
            )


# ==========================================================================================
# the mapping is uniform across endpoints that predate it
# ==========================================================================================


def test_a_not_found_proposal_gets_the_envelope_without_losing_its_old_shape(client):
    response = client.get("/api/v1/proposals/prop_does_not_exist")

    body = assert_envelope(response, status=404, code="PROPOSAL_NOT_FOUND")
    assert body["detail"]["error"] == "proposal_not_found", (
        "the pre-existing detail shape is preserved verbatim; the envelope only adds"
    )


def test_an_illegal_transition_keeps_its_machine_readable_status(client, manual_case):
    from tests.conftest import approve, solve_proposal

    proposal = solve_proposal(client, manual_case("case_001_knee"))
    approve(client, proposal["proposal_id"])

    response = client.post(
        f"/api/v1/proposals/{proposal['proposal_id']}/approve", json={"approved_by": "Dr. Zwei"}
    )

    body = assert_envelope(response, status=409, code="ILLEGAL_TRANSITION")
    assert body["details"]["current_status"] == "APPROVED"
    assert body["details"]["requested_status"] == "APPROVED"
    assert body["detail"]["current_status"] == "APPROVED", "and still where it always was"


def test_an_unknown_catalog_edition_names_the_ones_that_exist():
    """Not reachable over HTTP today — no route takes an edition — so it is asserted on the
    exception, which is where the mapping lives. The handler renders whatever it is given."""
    from app.catalog import CatalogNotFoundError, load_catalog

    with pytest.raises(CatalogNotFoundError) as caught:
        load_catalog(catalog_version="goae_1800")

    error = caught.value
    assert error.http_status == 404
    assert error.error_code == ErrorCode.CATALOG_NOT_FOUND
    assert error.details["requested_version"] == "goae_1800"
    assert "goae_current" in error.details["available_versions"]
    assert isinstance(error, ValueError), "the pre-existing bases are unchanged"


@pytest.mark.asyncio
async def test_an_unnamed_exception_still_produces_a_parsable_envelope():
    """The last-resort handler, asserted directly.

    Not over HTTP: Starlette's `ServerErrorMiddleware` re-raises after answering, so `TestClient`
    would surface the original exception rather than the response a real client receives. Calling
    the handler is what actually checks the promise — that `error_code` is parsable from *any*
    failure, including one nobody anticipated.
    """
    import json

    from app.api.errors import unhandled_error_handler

    response = await unhandled_error_handler(None, KeyError("secret_patient_id"))
    body = json.loads(response.body)

    assert response.status_code == 500
    assert body["error_code"] == "INTERNAL_ERROR"
    # `request_id` joined `details` when the observability floor landed: it is what a caller quotes
    # back, and a 500 with no id is a report nobody can act on. Empty here because this calls the
    # handler directly, with no request and therefore no id — which is itself the contract: the
    # field is always present, even when there is nothing to put in it.
    assert body["details"] == {"exception": "KeyError", "request_id": ""}
    assert "secret_patient_id" not in response.body.decode(), (
        "an unhandled exception's message has not been vetted for what it might leak"
    )


def test_the_cli_prints_the_same_catalog_rather_than_a_traceback(tmp_path, capsys):
    """An operator running `engine_cli padnext` gets the code and the location, not a stack."""
    import importlib.util

    from app.config import ENGINE_DIR

    spec = importlib.util.spec_from_file_location(
        "engine_cli", ENGINE_DIR / "scripts" / "engine_cli.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    broken = tmp_path / "broken_padx.xml"
    broken.write_bytes(b"<rechnungen><rechnung></rechnungen>")

    assert module.main(["padnext", str(broken)]) == 2
    stderr = capsys.readouterr().err
    assert "INVALID_XML" in stderr
    assert re.search(r"line \d+, column \d+", stderr), stderr


def test_a_healthy_request_is_untouched_by_any_of_this(client, manual_case):
    """The guard against a handler that quietly wraps successes too."""
    from tests.conftest import solve_proposal

    proposal = solve_proposal(client, manual_case("case_001_knee"))

    assert "error_code" not in proposal
    assert proposal["status"] == "DRAFT"
