"""`scripts/auto_verify_rules.py`: the two decisions that are made without a model in the loop.

The verification pass itself needs an API key and costs money, so it is not what this file tests.
What it tests is the logic that decides *whether a failed call is worth repeating* — a
misclassification there either abandons rules on a transient 429 or hammers a rejected credential
859 times — and the arithmetic `--report` prints, which is the number a human reads before deciding
to spend anything at all.

Neither test calls AWS. `boto3.client(...)` resolves the service model out of the installed
botocore wheel without a network round trip or a credential, so the `ClientError` instances below
are the real class, raised the way botocore raises it, with the real response shape.
"""

from __future__ import annotations

import csv
import importlib.util
import sys

import pytest

from app.config import ENGINE_DIR

botocore_exceptions = pytest.importorskip(
    "botocore.exceptions", reason="boto3 is curation tooling — pip install -r requirements-tooling.txt"
)
ClientError = botocore_exceptions.ClientError


def _load_script():
    """Load the script as a module.

    `sys.modules[...] = module` before `exec_module` is not optional here: the script uses
    `from __future__ import annotations`, so its dataclass field types are strings, and
    `@dataclass` resolves them by looking the defining module up in `sys.modules`. Skip the
    registration and every dataclass in the file raises at import.
    """
    spec = importlib.util.spec_from_file_location(
        "auto_verify_rules", ENGINE_DIR / "scripts" / "auto_verify_rules.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def script():
    return _load_script()


def _client_error(code: str, status: int) -> ClientError:
    """A botocore error shaped exactly as `bedrock-runtime` raises it."""
    return ClientError(
        {
            "Error": {"Code": code, "Message": f"synthetic {code}"},
            "ResponseMetadata": {"HTTPStatusCode": status, "RequestId": "test"},
        },
        "Converse",
    )


# ==============================================================================================
# bedrock retry classification
# ==============================================================================================


@pytest.mark.parametrize(
    "code, status",
    [
        ("ValidationException", 400),
        ("AccessDeniedException", 403),
        ("ResourceNotFoundException", 404),
    ],
)
def test_the_three_named_fatal_codes_are_not_retried(script, code, status):
    """A wrong model id, a model this account may not call, a model that does not exist.

    Three attempts would print the same message three times, so the run stops on the first one
    with the id it tried still in the error text.
    """
    assert script.bedrock_is_fatal(_client_error(code, status)) is True


@pytest.mark.parametrize(
    "code, status",
    [
        ("ThrottlingException", 429),
        ("TooManyRequestsException", 429),
        ("ServiceUnavailableException", 503),
        ("InternalServerException", 500),
        ("ModelTimeoutException", 408),
        ("ModelNotReadyException", 429),
    ],
)
def test_throttling_and_service_failures_are_retried(script, code, status):
    assert script.bedrock_is_fatal(_client_error(code, status)) is False


def test_an_unknown_4xx_is_fatal_and_an_unknown_5xx_is_not(script):
    """The fallback that keeps a code Bedrock adds tomorrow from being misclassified.

    A 4xx says the request is the problem and will be the problem again; a 5xx says the service
    was. Neither needs its code to be on a list first.
    """
    assert script.bedrock_is_fatal(_client_error("SomeNewClientException", 400)) is True
    assert script.bedrock_is_fatal(_client_error("SomeNewServerException", 502)) is False


def test_an_unknown_429_is_retried_even_though_it_is_a_4xx(script):
    """429 is the one 4xx that a second attempt can fix, and it is why this is not `status < 500`."""
    assert script.bedrock_is_fatal(_client_error("QuotaThing", 429)) is False


def test_a_missing_credential_is_fatal_although_it_carries_no_error_code(script):
    """`BotoCoreError` subclasses have no `response`, so the code-based path cannot see them.

    Without the name check these fall through to "retryable" and every rule in the backlog waits
    out two backoffs before being skipped for a reason that was fixed in the first millisecond.
    """
    assert script.bedrock_is_fatal(botocore_exceptions.NoCredentialsError()) is True
    assert script.bedrock_is_fatal(botocore_exceptions.NoRegionError()) is True


def test_a_dropped_connection_is_retried(script):
    """The other half of the same family: transient, and worth another go."""
    exc = botocore_exceptions.EndpointConnectionError(endpoint_url="https://example.invalid")
    assert script.bedrock_is_fatal(exc) is False
    assert script.bedrock_is_fatal(ConnectionError("reset by peer")) is False


def test_throttling_backs_off_exponentially_and_is_capped(script):
    delays = [script.bedrock_retry_delay(_client_error("ThrottlingException", 429), n) for n in (1, 2, 3)]
    assert delays == [5.0, 10.0, 20.0]
    assert script.bedrock_retry_delay(_client_error("ThrottlingException", 429), 99) == 60.0


def test_a_non_throttling_retry_keeps_the_shared_linear_delay(script):
    """Same 2s/4s ladder the base `Verifier` uses, so one provider does not stall a run."""
    exc = _client_error("InternalServerException", 500)
    assert [script.bedrock_retry_delay(exc, n) for n in (1, 2)] == [2.0, 4.0]


def test_the_verifier_delegates_both_hooks_to_the_module_level_classifiers(script):
    """The class is what the retry loop calls; the pure functions are what is tested above.

    A stub client keeps this off the network — the point is only that `BedrockVerifier` is wired to
    the classifier, and that `ClientError` is in a tuple the loop actually catches.
    """
    verifier = script.BedrockVerifier(
        "eu.anthropic.claude-opus-5", "high", usage=script.Usage(), client=object()
    )
    fatal = _client_error("ValidationException", 400)
    throttle = _client_error("ThrottlingException", 429)

    assert verifier.is_fatal(fatal) is True
    assert verifier.is_fatal(throttle) is False
    assert verifier._retry_delay(throttle, 1) == 5.0
    assert isinstance(fatal, verifier.FATAL + verifier.RETRYABLE)


def test_a_fatal_error_costs_exactly_one_attempt(script, monkeypatch):
    """The property the classification exists for, checked end to end through the retry loop."""
    verifier = script.BedrockVerifier(
        "eu.anthropic.claude-opus-5", "high", usage=script.Usage(), client=object()
    )
    calls = []

    def boom(_prompt):
        calls.append(1)
        raise _client_error("AccessDeniedException", 403)

    monkeypatch.setattr(verifier, "ask", boom)
    monkeypatch.setattr(script.time, "sleep", lambda _s: None)

    answer, error = verifier.ask_with_retries("prompt")
    assert answer == ""
    assert "AccessDeniedException" in error
    assert len(calls) == 1


def test_a_retryable_error_costs_the_full_attempt_budget(script, monkeypatch):
    verifier = script.BedrockVerifier(
        "eu.anthropic.claude-opus-5", "high", usage=script.Usage(), client=object()
    )
    calls = []

    def boom(_prompt):
        calls.append(1)
        raise _client_error("ThrottlingException", 429)

    monkeypatch.setattr(verifier, "ask", boom)
    monkeypatch.setattr(script.time, "sleep", lambda _s: None)

    answer, error = verifier.ask_with_retries("prompt")
    assert answer == ""
    assert "ThrottlingException" in error
    assert len(calls) == script.MAX_ATTEMPTS


# ==============================================================================================
# bedrock plumbing that has an answer without a call
# ==============================================================================================


def test_bedrock_usage_is_accounted_into_the_shared_counters(script):
    usage = script.Usage()
    usage.add_bedrock({"inputTokens": 1200, "outputTokens": 80, "totalTokens": 1280})
    usage.add_bedrock({"inputTokens": 800, "outputTokens": 20, "cacheReadInputTokens": 500})

    assert usage.input_tokens == 2000
    assert usage.output_tokens == 100
    assert usage.cache_read_tokens == 500
    usage.add_bedrock(None)  # a response without a usage block must not raise
    assert usage.input_tokens == 2000


def test_a_bedrock_model_id_finds_the_rate_its_bare_name_has(script):
    """`eu.anthropic.claude-opus-5-v1:0` and `claude-opus-5` are one model, not two rate rows."""
    assert script.pricing_key("eu.anthropic.claude-opus-5-v1:0") == "claude-opus-5"
    assert script.pricing_key("us.anthropic.claude-sonnet-5") == "claude-sonnet-5"
    assert script.pricing_key("anthropic.claude-haiku-4-5") == "claude-haiku-4-5"
    assert script.pricing_key("claude-opus-5") == "claude-opus-5"

    usage = script.Usage(input_tokens=1_000_000, output_tokens=1_000_000)
    assert usage.cost_usd("eu.anthropic.claude-opus-5") == usage.cost_usd("claude-opus-5")


def test_an_unmapped_model_still_reports_no_cost_rather_than_a_made_up_one(script):
    assert script.pricing_key("eu.meta.llama-4-maverick-v1:0") not in script.PRICING
    assert script.Usage(input_tokens=10_000).cost_usd("eu.meta.llama-4-maverick-v1:0") is None


def test_bedrock_is_last_in_the_auto_detect_order(script):
    """An AWS config file exists on more laptops than an Anthropic key does; it must not win."""
    assert list(script.PROVIDERS) == ["anthropic", "gemini", "bedrock"]


def test_the_bedrock_model_id_comes_from_the_env_when_the_flag_is_absent(script, monkeypatch):
    monkeypatch.delenv("BEDROCK_MODEL_ID", raising=False)
    assert script._default_model("bedrock") == script.DEFAULT_BEDROCK_MODEL_ID

    monkeypatch.setenv("BEDROCK_MODEL_ID", "eu.anthropic.claude-sonnet-5-v1:0")
    assert script._default_model("bedrock") == "eu.anthropic.claude-sonnet-5-v1:0"
    # The other providers have no env override and must be unaffected by it.
    assert script._default_model("anthropic") == script.PROVIDERS["anthropic"]["model"]


# ==============================================================================================
# --report math
# ==============================================================================================


def _table(script, tmp_path, name, kind, rows):
    """A `RuleTable` built through the real loader, so the report sees the real column handling."""
    path = tmp_path / name
    fieldnames = ["rule_id", "from_ziffer", "to_ziffer", "direction", "verified"]
    if kind == "factor_cap":
        fieldnames = ["rule_id", "ziffer", "max_factor", "verified"]
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames + ["ai_verdict"], lineterminator="\r\n")
        writer.writeheader()
        writer.writerows(rows)
    return script.RuleTable.load(path, kind)


def test_the_four_counts_partition_the_table_two_ways(script, tmp_path):
    """verified + unverified == total, and ai_verdict cuts across that partition.

    A NEEDS_HUMAN_REVIEW verdict leaves a row unverified without leaving it untouched, and the
    report has to be able to say which of those two a row is — that difference is the whole
    backlog number.
    """
    table = _table(
        script,
        tmp_path,
        "exclusions.csv",
        "exclusion",
        [
            # verified by a human, never seen by this script
            {"rule_id": "a", "from_ziffer": "1", "to_ziffer": "2", "verified": "true", "ai_verdict": ""},
            # verified by this script
            {"rule_id": "b", "from_ziffer": "3", "to_ziffer": "4", "verified": "true", "ai_verdict": "VERIFIED"},
            # asked, and sent to a human — unverified, but NOT untouched
            {"rule_id": "c", "from_ziffer": "5", "to_ziffer": "6", "verified": "false", "ai_verdict": "NEEDS_HUMAN_REVIEW"},
            # the actual backlog
            {"rule_id": "d", "from_ziffer": "7", "to_ziffer": "8", "verified": "false", "ai_verdict": ""},
            {"rule_id": "e", "from_ziffer": "9", "to_ziffer": "10", "verified": "", "ai_verdict": ""},
        ],
    )

    report = script.table_report(table)
    assert (report.total, report.verified, report.ai_verdict, report.untouched) == (5, 2, 2, 2)
    assert report.unverified == 3
    assert report.verified + report.unverified == report.total
    assert report.coverage_pct == pytest.approx(40.0)


def test_untouched_is_what_a_run_would_actually_ask_about(script, tmp_path):
    """`untouched` and `collect_candidates` must be the same set, or the report is decoration."""
    table = _table(
        script,
        tmp_path,
        "exclusions.csv",
        "exclusion",
        [
            {"rule_id": "a", "from_ziffer": "1", "to_ziffer": "2", "verified": "true", "ai_verdict": ""},
            {"rule_id": "c", "from_ziffer": "5", "to_ziffer": "6", "verified": "false", "ai_verdict": "NEEDS_HUMAN_REVIEW"},
            {"rule_id": "d", "from_ziffer": "7", "to_ziffer": "8", "verified": "false", "ai_verdict": ""},
        ],
    )
    candidates = script.collect_candidates([table], redo=False)

    assert script.table_report(table).untouched == len(candidates) == 1
    assert [c.rule_id for c in candidates] == ["d"]


def test_the_totals_row_sums_the_tables_and_weights_coverage_by_size(script, tmp_path):
    """Coverage is verified/total over both tables, not the mean of the two percentages."""
    big = _table(
        script,
        tmp_path,
        "exclusions.csv",
        "exclusion",
        [
            {"rule_id": f"e{i}", "from_ziffer": "1", "to_ziffer": "2", "verified": "true", "ai_verdict": ""}
            for i in range(9)
        ]
        + [{"rule_id": "e9", "from_ziffer": "1", "to_ziffer": "2", "verified": "false", "ai_verdict": ""}],
    )
    small = _table(
        script,
        tmp_path,
        "factor_caps.csv",
        "factor_cap",
        [{"rule_id": "c0", "ziffer": "52", "max_factor": "1.0", "verified": "false", "ai_verdict": ""}],
    )

    reports = [script.table_report(big), script.table_report(small)]
    total = script.overall_report(reports)

    assert (total.total, total.verified, total.untouched) == (11, 9, 2)
    # 9/11, not the mean of 90% and 0%.
    assert total.coverage_pct == pytest.approx(100.0 * 9 / 11)
    assert total.coverage_pct != pytest.approx((reports[0].coverage_pct + reports[1].coverage_pct) / 2)


def test_an_empty_table_reports_zero_coverage_rather_than_dividing_by_zero(script, tmp_path):
    table = _table(script, tmp_path, "exclusions.csv", "exclusion", [])
    assert script.table_report(table).coverage_pct == 0.0
    assert script.overall_report([]).coverage_pct == 0.0


def test_the_report_writes_nothing(script, tmp_path, capsys):
    """`--report` is a read. The CSV bytes must be identical afterwards, CRLF included."""
    table = _table(
        script,
        tmp_path,
        "exclusions.csv",
        "exclusion",
        [{"rule_id": "d", "from_ziffer": "7", "to_ziffer": "8", "verified": "false", "ai_verdict": ""}],
    )
    before = table.path.read_bytes()
    log_before = script.AUDIT_LOG.read_bytes() if script.AUDIT_LOG.exists() else None

    script.print_report([table], script.collect_candidates([table], redo=False), {}, "file")

    assert table.path.read_bytes() == before
    assert (script.AUDIT_LOG.read_bytes() if script.AUDIT_LOG.exists() else None) == log_before
    assert "d" in capsys.readouterr().out


# ==============================================================================================
# --order
# ==============================================================================================


def test_punkte_desc_puts_the_most_expensive_rule_first_and_is_stable(script, tmp_path):
    table = _table(
        script,
        tmp_path,
        "exclusions.csv",
        "exclusion",
        [
            {"rule_id": "cheap", "from_ziffer": "1", "to_ziffer": "2", "verified": "false", "ai_verdict": ""},
            {"rule_id": "rich", "from_ziffer": "3", "to_ziffer": "4", "verified": "false", "ai_verdict": ""},
            {"rule_id": "tie_a", "from_ziffer": "5", "to_ziffer": "6", "verified": "false", "ai_verdict": ""},
            {"rule_id": "tie_b", "from_ziffer": "5", "to_ziffer": "6", "verified": "false", "ai_verdict": ""},
            {"rule_id": "unknown", "from_ziffer": "999", "to_ziffer": "998", "verified": "false", "ai_verdict": ""},
        ],
    )
    entry = script.CatalogEntry
    catalog = {
        z: entry(ziffer=z, official_text="", punkte=p, section="", section_title="", annotations=())
        for z, p in {"1": 10, "2": 5, "3": 400, "4": 100, "5": 50, "6": 50}.items()
    }
    candidates = script.collect_candidates([table], redo=False)

    assert [c.rule_id for c in script.order_candidates(candidates, catalog, "file")] == [
        "cheap", "rich", "tie_a", "tie_b", "unknown",
    ]
    assert [c.rule_id for c in script.order_candidates(candidates, catalog, "punkte_desc")] == [
        "rich",      # 500
        "tie_a",     # 100, and first in the file
        "tie_b",     # 100
        "cheap",     # 15
        "unknown",   # 0 — no catalog entry, so it sorts last rather than raising
    ]


def test_a_factor_cap_is_weighted_by_its_one_ziffer(script, tmp_path):
    table = _table(
        script,
        tmp_path,
        "factor_caps.csv",
        "factor_cap",
        [{"rule_id": "cap_52", "ziffer": "52", "max_factor": "1.0", "verified": "false", "ai_verdict": ""}],
    )
    entry = script.CatalogEntry
    catalog = {
        "52": entry(ziffer="52", official_text="", punkte=70, section="", section_title="", annotations=())
    }
    candidate = script.collect_candidates([table], redo=False)[0]
    assert script.punkte_weight(candidate, catalog) == 70


def test_ordering_never_changes_the_candidate_set(script, tmp_path):
    """A sort may reorder the backlog. It may not add to it or drop from it."""
    table = _table(
        script,
        tmp_path,
        "exclusions.csv",
        "exclusion",
        [
            {"rule_id": f"r{i}", "from_ziffer": str(i), "to_ziffer": "2", "verified": "false", "ai_verdict": ""}
            for i in range(6)
        ],
    )
    entry = script.CatalogEntry
    catalog = {
        str(i): entry(ziffer=str(i), official_text="", punkte=i * 11, section="", section_title="", annotations=())
        for i in range(6)
    }
    candidates = script.collect_candidates([table], redo=False)
    ordered = script.order_candidates(candidates, catalog, "punkte_desc")

    assert {c.rule_id for c in ordered} == {c.rule_id for c in candidates}
    assert len(ordered) == len(candidates)
