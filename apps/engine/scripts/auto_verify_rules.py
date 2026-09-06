#!/usr/bin/env python3
"""Machine verification pass over the auto-extracted GOÄ rule tables.

    python scripts/auto_verify_rules.py --report         # where the backlog stands, no API calls
    python scripts/auto_verify_rules.py --dry-run        # first 5 rules, prompts + verdicts, no writes
    python scripts/auto_verify_rules.py                  # the whole backlog, saving after every rule
    python scripts/auto_verify_rules.py --only exclusions --limit 50
    python scripts/auto_verify_rules.py --order punkte_desc --limit 25   # the expensive rules first
    python scripts/auto_verify_rules.py --provider bedrock --dry-run
    python scripts/auto_verify_rules.py --revert-verdicts cap_auto_52,excl_auto_30_4

837 exclusions and 22 factor caps were read out of the Anmerkungen prose by `import_goae.py` and
carry `verified=false`. Under the shipped `UNVERIFIED_RULE_POLICY=warn` they enforce nothing, which
is why the engine's real rule coverage is 35 of 894. This script asks a model to read each rule back
against the official catalog text it was extracted from and say whether it is an unambiguous
deduction from that text.

**What this is not.** A model saying VERIFIED is not a Sachverständiger saying VERIFIED. Every rule
this script flips is stamped `source=ai_verified:<model>:<original source>` precisely so that the
distinction survives in the data: `manual_verification` remains the only provenance a human put
there. Read `ai_reasoning` before trusting any single row.

Design decisions worth knowing about:

* **The conservative default is structural, not prompted.** The prompt asks for one of two tokens,
  but the parser is what enforces safety: anything it cannot read as an unambiguous VERIFIED —
  malformed output, both tokens present, a refusal, an exception — becomes NEEDS_HUMAN_REVIEW. A
  bug in the model's formatting can only ever lose a verification, never invent one.
* **Progress is durable.** The CSV is rewritten (atomically, via a temp file and `os.replace`) after
  every single rule, and every verdict is also appended to a JSONL audit log. Re-running skips rows
  that already carry a verdict, so a crash, a Ctrl-C or an exhausted rate limit costs one rule.
* **Line endings are preserved.** The rule CSVs are CRLF and `rules_hash` is a SHA-256 over the
  file bytes, so rewriting them as LF would move the hash on every receipt for no reason.
* **The backlog can be walked in priority order.** `--order punkte_desc` puts the rules whose
  Ziffern are worth the most Punkte first, so a partial run (`--limit`) buys the most enforcement
  per euro spent. `--report` prints where the backlog stands without calling anything.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE_ROOT))

from app.config import CATALOG_PATH, RULES_DATA_DIR  # noqa: E402

# The two machine-extracted tables. `exclusions.manual.csv` and the other `.manual.` files are
# deliberately absent: a human verified those and this script has no business touching them.
EXCLUSIONS_CSV = RULES_DATA_DIR / "exclusions.csv"
FACTOR_CAPS_CSV = RULES_DATA_DIR / "factor_caps.csv"
AUDIT_LOG = RULES_DATA_DIR / "ai_verification_log.jsonl"

#: Columns this script appends. Order is fixed; `RuleStore` reads by name and ignores the rest.
AI_COLUMNS = ("ai_verdict", "ai_reasoning", "ai_model", "ai_checked_at")

VERIFIED = "VERIFIED"
NEEDS_REVIEW = "NEEDS_HUMAN_REVIEW"

DEFAULT_BEDROCK_REGION = "eu-central-1"

#: The Europe cross-region inference profile for Claude Opus 5. Bedrock addresses a model three
#: different ways — a bare foundation-model id (`anthropic.claude-opus-5`), a geography-prefixed
#: inference profile (`eu.`/`us.`/`apac.`), and a provisioned-throughput ARN — and which of them an
#: account may actually call depends on what it has enabled. Do not guess: ask the account.
#:
#:     aws bedrock list-inference-profiles --region eu-central-1 \
#:       --query "inferenceProfileSummaries[?contains(inferenceProfileId, 'anthropic')].inferenceProfileId"
#:     aws bedrock list-foundation-models --region eu-central-1 --by-provider anthropic \
#:       --query "modelSummaries[].modelId"
#:
#: Override per run with `--model` or once with `BEDROCK_MODEL_ID`. A wrong id is not a slow
#: failure: Bedrock answers `ValidationException` or `ResourceNotFoundException`, both of which
#: this script classifies FATAL, so it stops on the first rule with the id it tried in the message.
DEFAULT_BEDROCK_MODEL_ID = "eu.anthropic.claude-opus-5"

#: An anonymised billing-frequency export, if one is ever produced: `ziffer,count` over real
#: invoices. It does not exist yet, which is why `--order punkte_desc` uses Punkte as the proxy —
#: Punkte are published in the catalog, so the ordering is reproducible by anyone, but they say
#: what a position is worth once, not how often a practice bills it. Dropping a frequency file
#: here and reading it into the sort key is the intended upgrade path; nothing else changes.
FREQUENCY_CSV = RULES_DATA_DIR / "workbench" / "ziffer_frequency.csv"

#: Per provider: the env vars that count as credentials, and the default model.
PROVIDERS = {
    "anthropic": {
        "keys": ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"),
        "model": "claude-opus-5",
    },
    "gemini": {
        "keys": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
        # Flash rather than Pro because a free-tier key has no Pro quota (`gemini-3.1-pro-preview`
        # answers 429 RESOURCE_EXHAUSTED, `gemini-pro-latest` likewise). On a billed key, prefer
        # `--model gemini-3.1-pro-preview`: the exclusion rules turn on distinctions in German legal
        # prose — which of two Ziffern a sentence blocks, whether a range really covers a member —
        # and that is where a Flash-tier model is most likely to be confidently wrong.
        "model": "gemini-3.6-flash",
    },
    # Last in this dict on purpose: `_detect_provider` walks it in order, and an AWS config file
    # exists on far more developer machines than an Anthropic or a Gemini key does. A laptop that
    # happens to have `~/.aws/credentials` should not silently start billing a Bedrock account.
    "bedrock": {
        # boto3's own resolution chain is wider than any list of env vars (SSO caches, IMDS, the
        # container credential endpoint), so these are the cheap positives; `credential_files`
        # covers `aws configure` / `aws sso login` having been run at some point.
        "keys": (
            "AWS_ACCESS_KEY_ID",
            "AWS_PROFILE",
            "AWS_DEFAULT_PROFILE",
            "AWS_SESSION_TOKEN",
            "AWS_ROLE_ARN",
            "AWS_WEB_IDENTITY_TOKEN_FILE",
            "AWS_CONTAINER_CREDENTIALS_FULL_URI",
            "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI",
        ),
        "credential_files": ("~/.aws/credentials", "~/.aws/config"),
        "model": DEFAULT_BEDROCK_MODEL_ID,
        "env_model": "BEDROCK_MODEL_ID",
    },
}

DEFAULT_EFFORT = "high"
DEFAULT_SLEEP_SECONDS = 2.5
MAX_ATTEMPTS = 3
MAX_TOKENS = 4000

# Published rates, $/1M tokens, for the cost estimate only. A model absent from this table reports
# no cost rather than a made-up one.
PRICING = {
    "claude-opus-5": (5.0, 25.0),
    "claude-fable-5": (10.0, 50.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-haiku-4-5": (1.0, 5.0),
}


def pricing_key(model: str) -> str:
    """Normalise a provider's model id to a key in `PRICING`.

    Bedrock spells the same weights at greater length — an optional geography prefix for a
    cross-region inference profile, the `anthropic.` vendor prefix, and a version suffix — so
    `eu.anthropic.claude-opus-5-v1:0` and `claude-opus-5` name one model and should not need two
    rows in the rate table. Anything that does not reduce to a known key still returns "n/a"; the
    normalisation can only ever find a rate, never invent one.

    NOTE the rates it finds are Anthropic's first-party list price. AWS bills Bedrock separately,
    so a Bedrock run's cost line is an order-of-magnitude estimate — `main` says so in the summary.
    """
    key = (model or "").strip()
    for prefix in ("eu.", "us.", "apac.", "us-gov."):
        if key.startswith(prefix):
            key = key[len(prefix):]
            break
    if key.startswith("anthropic."):
        key = key[len("anthropic.") :]
    head, sep, tail = key.rpartition(":")
    if sep and tail.isdigit():  # ":0" — the Bedrock model version
        key = head
    head, sep, tail = key.rpartition("-v")
    if sep and tail.isdigit():  # "-v1" — the Bedrock model revision
        key = head
    return key


SYSTEM_PROMPT = """\
You are a strict, conservative German GOÄ billing auditor (Gebührenordnung für Ärzte). Your job is \
to verify whether a proposed machine-extracted rule is a 100% logically sound, unambiguous \
deduction from the provided official GOÄ text.

If the text explicitly and completely supports the rule, output VERIFIED.
If the text is ambiguous, incomplete, missing context, or requires external knowledge, output \
NEEDS_HUMAN_REVIEW.

NEVER GUESS. It is better to leave a rule unverified than to falsely verify it. A rule you verify \
will be enforced against real physicians' invoices and will tell a practice that money they billed \
is provably wrong. A false VERIFIED is a far worse outcome than a false NEEDS_HUMAN_REVIEW.

The rules were extracted automatically from Anmerkungen prose by a parser that makes exactly these \
mistakes. Check for every one of them before you answer:

1. DIRECTION. An exclusion is stored as a directed edge: "if A is billed, B is not billable \
beside it". German Anmerkungen state this in both word orders — "Die Leistung nach Nummer B ist \
neben den Leistungen nach den Nummern A nicht berechnungsfähig" means A blocks B, NOT B blocks A. \
If the quoted sentence does not pin the direction the rule claims, answer NEEDS_HUMAN_REVIEW.

2. MUTUAL vs ONE-WAY. A rule marked `mutual` asserts that each of the two positions blocks the \
other. A single sentence naming one direction does not establish that. Only answer VERIFIED for a \
mutual rule when the text (or a clearly reciprocal pair of statements in it) covers both \
directions.

3. RANGE EXPANSION. Quotes like "nach den Nummern 676 bis 692" were expanded by the parser into \
individual pairs. Verify that the specific Ziffer in this rule genuinely falls inside the range the \
quoted sentence names, and that the sentence is really enumerating a numeric range rather than, \
say, a section reference.

4. CONDITIONS THE ENGINE CANNOT SEE. The engine has NO concept of time, dates, quantity, \
Behandlungsfall, Sitzung, Kalenderjahr, or medical indication. It evaluates one invoice as a flat \
set of positions. If the quoted restriction is conditional or temporal — "im Behandlungsfall", \
"am selben Tag", "nur einmal", "in derselben Sitzung", "nur bei ...", "wenn ...", "es sei denn", \
"in der Regel" — then enforcing it as an unconditional block would be WRONG even though the \
sentence is real law. Answer NEEDS_HUMAN_REVIEW for those.

5. THE QUOTE MUST ACTUALLY SAY IT. If the quoted sentence does not name the Ziffern in question, or \
says something adjacent (a Zielleistung component relationship, a Zuschlag restriction, a \
Mindestdauer), do not stretch it. Answer NEEDS_HUMAN_REVIEW.

6. FACTOR CAPS. "nur mit dem einfachen Gebührensatz berechnungsfähig" means the fee factor may not \
exceed 1.0, so a claimed cap of 1.0 is supported. Any other claimed cap, or any softer wording, is \
NEEDS_HUMAN_REVIEW.

Answer in exactly this format and nothing else:

VERDICT: <VERIFIED or NEEDS_HUMAN_REVIEW>
REASONING: <one to three sentences, in English, naming the specific words in the official text that \
decide it>

Write the verdict token only on the VERDICT line. Do not write either token anywhere else in your \
answer."""


# ----------------------------------------------------------------------------------------------
# catalog
# ----------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class CatalogEntry:
    ziffer: str
    official_text: str
    punkte: int | None
    section: str
    section_title: str
    annotations: tuple[str, ...]

    def render(self) -> str:
        head = f"GOÄ {self.ziffer} — {self.official_text or '(no text in catalog)'}"
        meta = f"  Punkte: {self.punkte}  ·  Abschnitt {self.section} ({self.section_title})"
        if not self.annotations:
            return f"{head}\n{meta}\n  Amtliche Anmerkungen: (none recorded for this Ziffer)"
        notes = "\n".join(f"    - {a}" for a in self.annotations)
        return f"{head}\n{meta}\n  Amtliche Anmerkungen:\n{notes}"


def load_catalog(path: Path = CATALOG_PATH) -> dict[str, CatalogEntry]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    entries: dict[str, CatalogEntry] = {}
    for raw in payload["ziffern"]:
        entries[str(raw["ziffer"])] = CatalogEntry(
            ziffer=str(raw["ziffer"]),
            official_text=raw.get("official_text") or "",
            punkte=raw.get("punkte"),
            section=raw.get("section") or "",
            section_title=raw.get("section_title") or "",
            annotations=tuple(raw.get("annotations") or ()),
        )
    return entries


def _missing(ziffer: str) -> str:
    return f"GOÄ {ziffer} — NOT PRESENT in this catalog snapshot. No official text is available."


# ----------------------------------------------------------------------------------------------
# the rule tables
# ----------------------------------------------------------------------------------------------


@dataclass
class RuleTable:
    """One CSV, held in memory with its original column order, rewritten atomically after each row."""

    path: Path
    kind: str  # "exclusion" | "factor_cap"
    fieldnames: list[str]
    rows: list[dict[str, str]]

    @classmethod
    def load(cls, path: Path, kind: str) -> RuleTable:
        with open(path, encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            fieldnames = list(reader.fieldnames or [])
            rows = [dict(row) for row in reader if any((v or "").strip() for v in row.values())]
        for column in AI_COLUMNS:
            if column not in fieldnames:
                fieldnames.append(column)
        for row in rows:
            for column in AI_COLUMNS:
                row.setdefault(column, "")
                if row[column] is None:
                    row[column] = ""
            # DictReader parks unknown extra columns under None; dropping them keeps the writer honest.
            row.pop(None, None)
        return cls(path=path, kind=kind, fieldnames=fieldnames, rows=rows)

    def save(self) -> None:
        """Atomic: a crash mid-write leaves the previous good file, never a truncated one.

        `newline=""` plus an explicit CRLF terminator reproduces the importer's own output, so a
        row this script did not touch is byte-identical to what was there before.
        """
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(
                fh, fieldnames=self.fieldnames, lineterminator="\r\n", extrasaction="ignore"
            )
            writer.writeheader()
            writer.writerows(self.rows)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, self.path)


def _truthy(value: str | None) -> bool:
    """Same reading of the column as `app.rules.rule_store`, so "unverified" means one thing."""
    return str(value or "").strip().lower() in {"true", "1", "yes", "y"}


@dataclass
class Candidate:
    table: RuleTable
    row: dict[str, str]

    @property
    def rule_id(self) -> str:
        return self.row.get("rule_id", "")

    @property
    def kind(self) -> str:
        return self.table.kind

    def claim(self) -> str:
        """The rule restated as the sentence the engine would act on."""
        if self.kind == "factor_cap":
            return (
                f"GOÄ {self.row['ziffer']} may never be billed at a fee factor above "
                f"{self.row['max_factor']}."
            )
        a, b = self.row["from_ziffer"], self.row["to_ziffer"]
        if (self.row.get("direction") or "").strip() == "mutual":
            return (
                f"GOÄ {a} and GOÄ {b} are MUTUALLY exclusive: each blocks the other, and an "
                f"invoice containing both may charge only one of them."
            )
        return (
            f"ONE-WAY: if GOÄ {a} is billed, then GOÄ {b} is NOT separately billable beside it. "
            f"(The reverse is not asserted: GOÄ {b} does not block GOÄ {a}.)"
        )

    def ziffern(self) -> list[str]:
        if self.kind == "factor_cap":
            return [self.row["ziffer"]]
        return [self.row["from_ziffer"], self.row["to_ziffer"]]


def collect_candidates(tables: list[RuleTable], *, redo: bool) -> list[Candidate]:
    """Unverified rows that have no verdict yet — the resume point after a crash."""
    out: list[Candidate] = []
    for table in tables:
        for row in table.rows:
            if _truthy(row.get("verified")):
                continue
            if not redo and (row.get("ai_verdict") or "").strip():
                continue
            out.append(Candidate(table=table, row=row))
    return out


def punkte_weight(candidate: Candidate, catalog: dict[str, CatalogEntry]) -> int:
    """The summed Punkte of every Ziffer the rule touches — 0 for a Ziffer the catalog lacks."""
    return sum(
        (catalog[z].punkte or 0) for z in candidate.ziffern() if z in catalog
    )


def order_candidates(
    candidates: list[Candidate], catalog: dict[str, CatalogEntry], order: str
) -> list[Candidate]:
    """Decide which rules a partial run spends its budget on.

    `file` keeps the CSV's own order, which is the importer's, which is the catalog's — the right
    default because it is the one a reviewer reading the diff can follow.

    `punkte_desc` is a deliberately transparent proxy for billing importance: a rule over Ziffern
    worth many Punkte guards more money per invoice than one over a 30-Punkte position, and Punkte
    are published in the catalog, so anyone can reproduce the ordering exactly. It is a proxy and
    not the thing itself — see `FREQUENCY_CSV` for what would replace it. The sort is stable, so
    rules of equal weight stay in file order.
    """
    if order == "punkte_desc":
        return sorted(candidates, key=lambda c: -punkte_weight(c, catalog))
    return candidates


# ----------------------------------------------------------------------------------------------
# prompting
# ----------------------------------------------------------------------------------------------


def build_user_prompt(candidate: Candidate, catalog: dict[str, CatalogEntry]) -> str:
    blocks = [
        catalog[z].render() if z in catalog else _missing(z) for z in candidate.ziffern()
    ]
    row = candidate.row
    lines = [
        "## Official GOÄ text for every Ziffer this rule touches",
        "",
        "\n\n".join(blocks),
        "",
        "## The sentence the rule was extracted from",
        "",
        f'  "{row.get("quote", "").strip()}"',
        "",
        f"  Legal basis recorded by the extractor: {row.get('legal_basis', '').strip() or '(none)'}",
        f"  Extraction method: {row.get('source', '').strip() or '(unknown)'}",
        "",
        "## Proposed rule",
        "",
        f"  rule_id: {candidate.rule_id}",
        f"  type:    {'factor cap (§ 5 GOÄ)' if candidate.kind == 'factor_cap' else 'exclusion (Nebeneinanderberechnung)'}",
        f"  claim:   {candidate.claim()}",
        "",
        "Is this claim a 100% logically sound, unambiguous deduction from the official text above?",
        "",
        "Verdict:",
    ]
    return "\n".join(lines)


def parse_verdict(text: str) -> tuple[str, str]:
    """Read the model's answer. Anything not unambiguously VERIFIED becomes NEEDS_HUMAN_REVIEW.

    This is the safety property of the whole script, so it is deliberately paranoid: the verdict is
    taken from the `VERDICT:` line alone, and a line naming both tokens — or naming neither — falls
    through to review. Reasoning is returned whole either way, so nothing is lost for the audit.
    """
    raw = (text or "").strip()
    reasoning = raw
    verdict_line = ""
    for line in raw.splitlines():
        stripped = line.strip().lstrip("*# ").strip()
        if stripped.upper().startswith("VERDICT:"):
            verdict_line = stripped.split(":", 1)[1].strip()
            break

    if not verdict_line:
        return NEEDS_REVIEW, reasoning or "(empty response from the model)"

    token = verdict_line.upper()
    says_verified = VERIFIED in token
    says_review = NEEDS_REVIEW in token
    # NEEDS_HUMAN_REVIEW does not contain "VERIFIED" as a substring, so these are independent
    # signals and "both" genuinely means the model contradicted itself.
    if says_verified and not says_review:
        return VERIFIED, reasoning
    return NEEDS_REVIEW, reasoning


# ----------------------------------------------------------------------------------------------
# the API
# ----------------------------------------------------------------------------------------------


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    #: Reasoning tokens, where the provider reports them separately from the answer.
    thinking_tokens: int = 0

    def add_anthropic(self, usage) -> None:
        self.input_tokens += getattr(usage, "input_tokens", 0) or 0
        self.output_tokens += getattr(usage, "output_tokens", 0) or 0
        self.cache_read_tokens += getattr(usage, "cache_read_input_tokens", 0) or 0
        self.cache_write_tokens += getattr(usage, "cache_creation_input_tokens", 0) or 0

    def add_gemini(self, usage) -> None:
        if usage is None:
            return
        self.input_tokens += getattr(usage, "prompt_token_count", 0) or 0
        self.output_tokens += getattr(usage, "candidates_token_count", 0) or 0
        self.thinking_tokens += getattr(usage, "thoughts_token_count", 0) or 0
        self.cache_read_tokens += getattr(usage, "cached_content_token_count", 0) or 0

    def add_bedrock(self, usage) -> None:
        """Converse reports usage as a plain dict with camelCase keys.

        The two cache counters are only present when a request actually used a cache point; this
        script sends none, so they are read defensively rather than assumed.
        """
        if not usage:
            return
        self.input_tokens += usage.get("inputTokens", 0) or 0
        self.output_tokens += usage.get("outputTokens", 0) or 0
        self.cache_read_tokens += usage.get("cacheReadInputTokens", 0) or 0
        self.cache_write_tokens += usage.get("cacheWriteInputTokens", 0) or 0

    def cost_usd(self, model: str) -> float | None:
        """None when the model is not in the rate table — better than a confidently wrong number."""
        key = pricing_key(model)
        if key not in PRICING:
            return None
        rate_in, rate_out = PRICING[key]
        billable_in = self.input_tokens + self.cache_write_tokens * 1.25 + self.cache_read_tokens * 0.1
        billable_out = self.output_tokens + self.thinking_tokens
        return (billable_in * rate_in + billable_out * rate_out) / 1_000_000


class Verifier:
    """One API call per rule, with bounded retries around the transient failures.

    Subclasses supply `ask` plus the two exception sets the shared retry loop needs: FATAL failures
    that three attempts would reproduce identically (a rejected key, an unknown model id), and
    RETRYABLE ones that are worth another go (rate limits, 5xx, a dropped connection).
    """

    FATAL: tuple[type[BaseException], ...] = ()
    RETRYABLE: tuple[type[BaseException], ...] = ()

    def __init__(self, model: str, effort: str, *, usage: Usage) -> None:
        self.model = model
        self.effort = effort
        self.usage = usage

    def ask(self, user_prompt: str) -> str:
        raise NotImplementedError

    def is_fatal(self, exc: BaseException) -> bool:
        """Would three attempts reproduce this identically? Overridden where the class is coarser
        than the failure — Gemini raises one `ClientError` for both a rejected key and a 429."""
        return isinstance(exc, self.FATAL)

    def _retry_delay(self, exc: BaseException, attempt: int) -> float:
        return 2.0 * attempt

    def ask_with_retries(self, user_prompt: str) -> tuple[str, str | None]:
        """Returns (answer_text, error). On terminal failure the answer is an empty string."""
        last = ""
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                return self.ask(user_prompt), None
            except (self.FATAL + self.RETRYABLE) as exc:
                if self.is_fatal(exc):
                    return "", f"{type(exc).__name__}: {exc}"
                last = f"{type(exc).__name__}: {exc}"
                wait = self._retry_delay(exc, attempt)
            if attempt < MAX_ATTEMPTS:
                print(f"      ! {last[:160]} — retry {attempt}/{MAX_ATTEMPTS - 1} in {wait:.0f}s", flush=True)
                time.sleep(wait)
        return "", last


class AnthropicVerifier(Verifier):
    def __init__(self, model: str, effort: str, *, usage: Usage) -> None:
        super().__init__(model, effort, usage=usage)
        import anthropic  # imported here so --help works without the SDK installed

        # `max_retries=0`: the retry policy is ours, so that a skip is logged as a skip rather
        # than disappearing into the SDK's backoff.
        self.client = anthropic.Anthropic(max_retries=0, timeout=120.0)
        self.FATAL = (
            anthropic.BadRequestError,
            anthropic.AuthenticationError,
            anthropic.PermissionDeniedError,
            anthropic.NotFoundError,
        )
        self.RETRYABLE = (
            anthropic.RateLimitError,
            anthropic.APIStatusError,
            anthropic.APIConnectionError,
            anthropic.APITimeoutError,
        )
        self._rate_limit = anthropic.RateLimitError

    def _retry_delay(self, exc: BaseException, attempt: int) -> float:
        if isinstance(exc, self._rate_limit):
            return float(exc.response.headers.get("retry-after", "30") or 30)
        return 2.0 * attempt

    def ask(self, user_prompt: str) -> str:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=MAX_TOKENS,
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    # The system prompt is byte-identical on every call; caching it is free money
                    # if it clears the model's minimum cacheable prefix.
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            # Adaptive thinking: this is a legal-reasoning task where a wrong VERIFIED is expensive.
            thinking={"type": "adaptive"},
            output_config={"effort": self.effort},
            messages=[{"role": "user", "content": user_prompt}],
        )
        self.usage.add_anthropic(response.usage)
        if response.stop_reason == "refusal":
            detail = getattr(response, "stop_details", None)
            return f"VERDICT: {NEEDS_REVIEW}\nREASONING: the model declined to answer ({detail})."
        return "".join(b.text for b in response.content if b.type == "text").strip()


class GeminiVerifier(Verifier):
    """The same contract against the Google Gen AI SDK.

    `temperature=0` rather than a thinking budget: the answer is a two-token classification, and
    what matters for a verification pass is that re-running a rule gives the same verdict.
    """

    def __init__(self, model: str, effort: str, *, usage: Usage) -> None:
        super().__init__(model, effort, usage=usage)
        from google import genai
        from google.genai import errors, types

        self._types = types
        self.client = genai.Client()
        self._config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0.0,
            max_output_tokens=MAX_TOKENS,
            # Gemini's safety filters have nothing useful to say about fee-schedule prose, and a
            # blocked candidate would read as a malformed answer. Ask for the least intervention
            # the API offers on each category; anything still blocked falls through to review.
            safety_settings=[
                types.SafetySetting(category=c, threshold="BLOCK_ONLY_HIGH")
                for c in (
                    "HARM_CATEGORY_HARASSMENT",
                    "HARM_CATEGORY_HATE_SPEECH",
                    "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    "HARM_CATEGORY_DANGEROUS_CONTENT",
                )
            ],
        )
        self.FATAL = (errors.ClientError,)
        self.RETRYABLE = (errors.ServerError, errors.APIError, ConnectionError, TimeoutError)

    def is_fatal(self, exc: BaseException) -> bool:
        """A 429 arrives as `ClientError` alongside the genuinely fatal 400/401/403/404.

        Treating the whole class as fatal would abandon a rule the moment a per-minute quota
        refilled a second later, so 429 is pulled back out and retried with a long backoff.
        """
        code = getattr(exc, "code", None)
        if code == 429:
            return False
        return isinstance(exc, self.FATAL)

    def _retry_delay(self, exc: BaseException, attempt: int) -> float:
        # Free-tier quotas refill per minute, so a 429 is worth a real wait rather than 2 seconds.
        if getattr(exc, "code", None) == 429:
            return 30.0 * attempt
        return 2.0 * attempt

    def ask(self, user_prompt: str) -> str:
        response = self.client.models.generate_content(
            model=self.model, contents=user_prompt, config=self._config
        )
        self.usage.add_gemini(getattr(response, "usage_metadata", None))
        text = (response.text or "").strip()
        if not text:
            # A safety block or an empty candidate. Say so rather than returning "", so the row
            # records why it went to review instead of looking like a parser failure.
            feedback = getattr(response, "prompt_feedback", None)
            finish = ""
            if getattr(response, "candidates", None):
                finish = str(getattr(response.candidates[0], "finish_reason", ""))
            return (
                f"VERDICT: {NEEDS_REVIEW}\n"
                f"REASONING: the model returned no text (finish_reason={finish or 'unknown'}, "
                f"prompt_feedback={feedback})."
            )
        return text


# -- bedrock -----------------------------------------------------------------------------------
#
# botocore models Bedrock's failures as one `ClientError` carrying an error code, not as a class
# per failure, so the retry decision is made from that code rather than from `isinstance`. Keeping
# the classifier a module-level pure function — rather than a method reaching into `self` — is what
# lets it be unit-tested against a synthetic error without a client, a region or a credential.

#: Three attempts would reproduce these identically: the request is wrong, or this account may not
#: call this model. Retrying is only a slower way to print the same message.
BEDROCK_FATAL_CODES = frozenset(
    {
        "ValidationException",
        "AccessDeniedException",
        "ResourceNotFoundException",
        "UnrecognizedClientException",
        "InvalidSignatureException",
        "ExpiredTokenException",
        "SerializationException",
        "ModelErrorException",
    }
)

#: Worth another go: the service was busy, throttling, or briefly broken.
BEDROCK_THROTTLE_CODES = frozenset({"ThrottlingException", "TooManyRequestsException"})
BEDROCK_RETRYABLE_CODES = BEDROCK_THROTTLE_CODES | {
    "ServiceUnavailableException",
    "InternalServerException",
    "InternalFailure",
    "ServiceInternalException",
    "ModelTimeoutException",
    "ModelNotReadyException",
    "RequestTimeout",
    "RequestTimeoutException",
}

#: `BotoCoreError` subclasses carry no error code — these are the ones that mean "this process is
#: not configured to call AWS at all", which no amount of retrying fixes. Anything else in that
#: family (a dropped connection, a read timeout, a DNS blip) falls through to retryable.
BEDROCK_FATAL_EXCEPTIONS = frozenset(
    {
        "NoCredentialsError",
        "PartialCredentialsError",
        "CredentialRetrievalError",
        "NoRegionError",
        "ProfileNotFound",
        "UnknownServiceError",
        "ParamValidationError",
        "InvalidRegionError",
    }
)


def bedrock_error_code(exc: BaseException) -> str:
    response = getattr(exc, "response", None)
    if not isinstance(response, dict):
        return ""
    error = response.get("Error")
    if not isinstance(error, dict):
        return ""
    return str(error.get("Code") or "")


def bedrock_http_status(exc: BaseException) -> int | None:
    response = getattr(exc, "response", None)
    if not isinstance(response, dict):
        return None
    meta = response.get("ResponseMetadata")
    if not isinstance(meta, dict):
        return None
    status = meta.get("HTTPStatusCode")
    return status if isinstance(status, int) else None


def bedrock_is_fatal(exc: BaseException) -> bool:
    """Would three attempts reproduce this identically?

    Named codes decide first. An unrecognised code falls back to the HTTP status, which answers the
    same question generically: a 4xx other than 429 means the request itself is the problem, and
    anything else (5xx, no status at all — a connection that never got an HTTP answer) is worth
    retrying. New Bedrock error codes therefore classify sensibly without this list being updated.
    """
    code = bedrock_error_code(exc)
    if code in BEDROCK_RETRYABLE_CODES:
        return False
    if code in BEDROCK_FATAL_CODES:
        return True
    if type(exc).__name__ in BEDROCK_FATAL_EXCEPTIONS:
        return True
    status = bedrock_http_status(exc)
    if status == 429:
        return False
    return status is not None and 400 <= status < 500


def bedrock_retry_delay(exc: BaseException, attempt: int) -> float:
    """Throttling gets exponential backoff; everything else keeps the shared linear one.

    Bedrock's per-account TPM quota refills continuously rather than on a minute boundary, so
    doubling from a few seconds beats Gemini's flat 30s wait — and the cap keeps a run that has hit
    a hard quota from stalling for minutes per rule instead of skipping and moving on.
    """
    if bedrock_error_code(exc) in BEDROCK_THROTTLE_CODES:
        return min(5.0 * (2 ** (attempt - 1)), 60.0)
    return 2.0 * attempt


class BedrockVerifier(Verifier):
    """The same contract against Amazon Bedrock's Converse API, via boto3.

    Converse rather than `invoke_model` because it takes `system` and `messages` in one shape for
    every vendor on Bedrock, so switching the model id is the only change needed to compare, say,
    Claude against another model on the same 859 rules.

    `temperature=0` for the reason the Gemini verifier gives: the answer is a two-token
    classification and re-running a rule must give the same verdict. That also rules out extended
    thinking, which Bedrock only serves at temperature 1 — so `--effort` is recorded in the audit
    log but does not reach the API here, exactly as it does not for Gemini.
    """

    def __init__(self, model: str, effort: str, *, usage: Usage, client=None) -> None:
        super().__init__(model, effort, usage=usage)
        import boto3  # imported here so --help and --report work without boto3 installed
        from botocore.config import Config
        from botocore.exceptions import BotoCoreError, ClientError

        self.region = os.environ.get("BEDROCK_REGION") or DEFAULT_BEDROCK_REGION
        # `max_attempts=1` means one attempt, no botocore-internal retries: the retry policy is
        # ours, so that a skip is logged as a skip rather than disappearing into botocore's backoff.
        self.client = client or boto3.client(
            "bedrock-runtime",
            region_name=self.region,
            config=Config(
                retries={"max_attempts": 1, "mode": "standard"},
                connect_timeout=10,
                read_timeout=120,
            ),
        )
        # Both tuples exist only so the shared retry loop knows what to catch; `is_fatal` below is
        # what actually decides, because botocore raises one class for a rejected key and a 429.
        self.FATAL = (ClientError,)
        self.RETRYABLE = (BotoCoreError, ConnectionError, TimeoutError)

    def is_fatal(self, exc: BaseException) -> bool:
        return bedrock_is_fatal(exc)

    def _retry_delay(self, exc: BaseException, attempt: int) -> float:
        return bedrock_retry_delay(exc, attempt)

    def ask(self, user_prompt: str) -> str:
        response = self.client.converse(
            modelId=self.model,
            system=[{"text": SYSTEM_PROMPT}],
            messages=[{"role": "user", "content": [{"text": user_prompt}]}],
            inferenceConfig={"maxTokens": MAX_TOKENS, "temperature": 0.0},
        )
        self.usage.add_bedrock(response.get("usage"))

        blocks = (response.get("output") or {}).get("message", {}).get("content") or []
        text = "".join(
            b["text"] for b in blocks if isinstance(b, dict) and isinstance(b.get("text"), str)
        ).strip()
        if not text:
            # A guardrail intervention, a content filter, or an empty candidate. Say which, so the
            # row records why it went to review instead of looking like a parser failure.
            return (
                f"VERDICT: {NEEDS_REVIEW}\n"
                f"REASONING: Bedrock returned no text "
                f"(stopReason={response.get('stopReason') or 'unknown'})."
            )
        return text


def make_verifier(provider: str, model: str, effort: str, *, usage: Usage) -> Verifier:
    if provider == "gemini":
        return GeminiVerifier(model, effort, usage=usage)
    if provider == "bedrock":
        return BedrockVerifier(model, effort, usage=usage)
    return AnthropicVerifier(model, effort, usage=usage)


# ----------------------------------------------------------------------------------------------
# applying a verdict
# ----------------------------------------------------------------------------------------------


def apply_verdict(candidate: Candidate, verdict: str, reasoning: str, model: str) -> None:
    """Write the verdict onto the row. Only VERIFIED touches the `verified` column.

    The `source` rewrite is the point: a rule this script verified must never be mistakable for one
    a Sachverständiger signed off. The original extraction method is kept in the same string so the
    lineage does not go missing.
    """
    row = candidate.row
    row["ai_verdict"] = verdict
    row["ai_reasoning"] = " ".join(reasoning.split())
    row["ai_model"] = model
    row["ai_checked_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if verdict == VERIFIED:
        original = (row.get("source") or "").strip()
        if not original.startswith("ai_verified:"):
            row["source"] = f"ai_verified:{model}:{original}"
        row["verified"] = "true"
        row["verified_at"] = date.today().isoformat()


def log_result(record: dict) -> None:
    with open(AUDIT_LOG, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def revert(rule_ids: set[str], tables: list[RuleTable]) -> int:
    """Undo AI verdicts for named rules — the escape hatch when a golden case exposes a bad one."""
    reverted = 0
    for table in tables:
        touched = False
        for row in table.rows:
            if row.get("rule_id") not in rule_ids:
                continue
            if not (row.get("source") or "").startswith("ai_verified:"):
                if not (row.get("ai_verdict") or "").strip():
                    continue
            row["verified"] = "false"
            row["verified_at"] = ""
            source = (row.get("source") or "")
            if source.startswith("ai_verified:"):
                row["source"] = source.split(":", 2)[2] if source.count(":") >= 2 else ""
            row["ai_verdict"] = NEEDS_REVIEW
            row["ai_reasoning"] = (
                f"REVERTED by operator on {date.today().isoformat()}. "
                f"Previous: {row.get('ai_reasoning', '')}"
            )
            reverted += 1
            touched = True
        if touched:
            table.save()
    return reverted


# ----------------------------------------------------------------------------------------------
# the state report
# ----------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class TableReport:
    """Where one table stands. Four counts that add up two different ways, on purpose.

    `verified + unverified == total` partitions the table by what the engine will enforce;
    `ai_verdict` cuts across that partition, because a NEEDS_HUMAN_REVIEW verdict leaves a row
    unverified but is not the same thing as never having been looked at. `untouched` is the
    backlog this script still has work to do on.
    """

    name: str
    total: int
    verified: int
    ai_verdict: int
    untouched: int

    @property
    def unverified(self) -> int:
        return self.total - self.verified

    @property
    def coverage_pct(self) -> float:
        return 100.0 * self.verified / self.total if self.total else 0.0


def table_report(table: RuleTable) -> TableReport:
    verified = sum(1 for r in table.rows if _truthy(r.get("verified")))
    ai_verdict = sum(1 for r in table.rows if (r.get("ai_verdict") or "").strip())
    untouched = sum(
        1
        for r in table.rows
        if not _truthy(r.get("verified")) and not (r.get("ai_verdict") or "").strip()
    )
    return TableReport(
        name=table.path.name,
        total=len(table.rows),
        verified=verified,
        ai_verdict=ai_verdict,
        untouched=untouched,
    )


def overall_report(reports: list[TableReport]) -> TableReport:
    return TableReport(
        name="TOTAL",
        total=sum(r.total for r in reports),
        verified=sum(r.verified for r in reports),
        ai_verdict=sum(r.ai_verdict for r in reports),
        untouched=sum(r.untouched for r in reports),
    )


def print_report(
    tables: list[RuleTable],
    candidates: list[Candidate],
    catalog: dict[str, CatalogEntry],
    order: str,
) -> None:
    """Print the state of the backlog. Calls nothing, writes nothing."""
    reports = [table_report(t) for t in tables]
    total = overall_report(reports)

    print("=" * 96)
    print("GOÄ rule verification — state report")
    print("=" * 96)
    print(f"  {'table':<26} {'rows':>7} {'verified':>10} {'ai_verdict':>11} {'untouched':>10} {'coverage':>9}")
    print("  " + "-" * 78)
    for r in reports + [total]:
        if r is total:
            print("  " + "-" * 78)
        print(
            f"  {r.name:<26} {r.total:>7} {r.verified:>10} {r.ai_verdict:>11} "
            f"{r.untouched:>10} {r.coverage_pct:>8.1f}%"
        )
    print()
    print(f"  candidates awaiting a verdict : {len(candidates)}   (order: {order})")
    if not FREQUENCY_CSV.exists():
        print(f"  frequency file                : absent ({FREQUENCY_CSV}) — punkte_desc is the proxy")
    print()
    print(f"  next {min(10, len(candidates))} under this order:")
    if not candidates:
        print("    (none — every rule is verified or already carries a verdict)")
    for i, candidate in enumerate(candidates[:10], 1):
        ziffern = ", ".join(candidate.ziffern())
        weight = punkte_weight(candidate, catalog)
        print(f"    {i:>2}. {candidate.rule_id:<24} {candidate.kind:<11} Ziffern {ziffern:<12} ({weight} Punkte)")
    print("=" * 96)


# ----------------------------------------------------------------------------------------------
# main
# ----------------------------------------------------------------------------------------------


@dataclass
class Tally:
    verified: int = 0
    review: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)


def _has_credentials(provider: str) -> bool:
    """An env var, or — for Bedrock — a config file `aws configure` / `aws sso login` wrote.

    This is deliberately a weaker test than boto3's own resolution chain: it decides which provider
    to *default* to, and the real answer still comes from the first API call. A machine with an AWS
    config file but no usable session gets a fatal `UnrecognizedClientException` on rule 1, which
    is a clearer failure than silently defaulting to a provider whose key is also absent.
    """
    spec = PROVIDERS[provider]
    if any(os.environ.get(k) for k in spec["keys"]):
        return True
    return any(Path(f).expanduser().exists() for f in spec.get("credential_files", ()))


def _default_model(provider: str) -> str:
    """The provider's default, overridable once via env rather than on every command line."""
    spec = PROVIDERS[provider]
    env_var = spec.get("env_model")
    return (env_var and os.environ.get(env_var)) or spec["model"]


def _detect_provider() -> str:
    """Whichever provider has a key in the environment; Anthropic wins a tie."""
    for name in PROVIDERS:
        if _has_credentials(name):
            return name
    return "anthropic"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify auto-extracted GOÄ rules against the official catalog text.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="process the first 5 rules, print the full prompt / response / reasoning, save nothing",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="print where the backlog stands (per table, coverage, next 10) and exit; no API calls",
    )
    parser.add_argument("--limit", type=int, default=0, help="stop after N rules (0 = all)")
    parser.add_argument(
        "--order",
        default="file",
        choices=("file", "punkte_desc"),
        help="candidate order: file (the CSV's own) or punkte_desc (highest summed Punkte first, "
        "a transparent proxy for billing importance — see FREQUENCY_CSV)",
    )
    parser.add_argument(
        "--only",
        choices=("exclusions", "factor_caps"),
        help="restrict to one table (default: both)",
    )
    parser.add_argument(
        "--provider",
        choices=tuple(PROVIDERS),
        help="which API to call (default: whichever has a key in the environment)",
    )
    parser.add_argument(
        "--model",
        help="default: the provider's default (see PROVIDERS at the top of this file); for "
        "bedrock, BEDROCK_MODEL_ID overrides that default and BEDROCK_REGION picks the region",
    )
    parser.add_argument(
        "--effort",
        default=DEFAULT_EFFORT,
        choices=("low", "medium", "high", "xhigh", "max"),
        help=f"reasoning effort (default {DEFAULT_EFFORT})",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=DEFAULT_SLEEP_SECONDS,
        help=f"seconds between API calls (default {DEFAULT_SLEEP_SECONDS})",
    )
    parser.add_argument(
        "--redo",
        action="store_true",
        help="re-ask rules that already carry a verdict (default: skip them, so a run resumes)",
    )
    parser.add_argument(
        "--revert-verdicts",
        metavar="RULE_IDS",
        help="comma-separated rule ids to un-verify, then exit (for a rule a golden case caught)",
    )
    args = parser.parse_args(argv)
    args.provider = args.provider or _detect_provider()
    args.model = args.model or _default_model(args.provider)

    tables: list[RuleTable] = []
    if args.only != "factor_caps":
        tables.append(RuleTable.load(EXCLUSIONS_CSV, "exclusion"))
    if args.only != "exclusions":
        tables.append(RuleTable.load(FACTOR_CAPS_CSV, "factor_cap"))

    if args.revert_verdicts:
        ids = {r.strip() for r in args.revert_verdicts.split(",") if r.strip()}
        count = revert(ids, tables)
        print(f"reverted {count} rule(s) to verified=false: {', '.join(sorted(ids))}")
        return 0

    catalog = load_catalog()
    candidates = order_candidates(
        collect_candidates(tables, redo=args.redo), catalog, args.order
    )
    total_unverified = sum(
        1 for t in tables for r in t.rows if not _truthy(r.get("verified"))
    )

    if args.report:
        print_report(tables, candidates, catalog, args.order)
        return 0

    if args.dry_run:
        candidates = candidates[:5]
    elif args.limit:
        candidates = candidates[: args.limit]

    print("=" * 96)
    print("GOÄ auto-extracted rule verification")
    print("=" * 96)
    print(f"  catalog        : {CATALOG_PATH.name}  ({len(catalog)} Ziffern)")
    print(f"  tables         : {', '.join(t.path.name for t in tables)}")
    print(f"  unverified     : {total_unverified}")
    print(f"  to process now : {len(candidates)}")
    print(f"  order          : {args.order}")
    print(f"  provider       : {args.provider}")
    print(f"  model / effort : {args.model} / {args.effort}")
    if args.provider == "bedrock":
        print(f"  region         : {os.environ.get('BEDROCK_REGION') or DEFAULT_BEDROCK_REGION}")
    print(f"  mode           : {'DRY RUN — nothing will be written' if args.dry_run else 'LIVE — CSV saved after every rule'}")
    print("=" * 96)
    print()

    if not candidates:
        print("Nothing to do: every rule already carries a verdict or is verified.")
        return 0

    if not _has_credentials(args.provider):
        expected = " / ".join(PROVIDERS[args.provider]["keys"])
        print(f"!! No {expected} in the environment.")
        print("!! Printing the rendered prompts so they can be reviewed, then stopping without")
        print("!! calling the API. Export a key and re-run to get verdicts.")
        print()
        print("SYSTEM PROMPT")
        print("-" * 96)
        print(SYSTEM_PROMPT)
        print("-" * 96)
        print()
        for i, candidate in enumerate(candidates[:5], 1):
            print(f"[{i}] {candidate.rule_id}  ({candidate.kind})")
            print("-" * 96)
            print(build_user_prompt(candidate, catalog))
            print("-" * 96)
            print()
        return 2

    usage = Usage()
    verifier = make_verifier(args.provider, args.model, args.effort, usage=usage)
    tally = Tally()

    for i, candidate in enumerate(candidates, 1):
        prompt = build_user_prompt(candidate, catalog)
        header = f"[{i}/{len(candidates)}] {candidate.rule_id}"

        if args.dry_run:
            print("=" * 96)
            print(f"{header}   ({candidate.kind}, table {candidate.table.path.name})")
            print("=" * 96)
            print()
            print("--- SYSTEM PROMPT " + "-" * 78)
            print(SYSTEM_PROMPT)
            print()
            print("--- USER PROMPT " + "-" * 80)
            print(prompt)
            print()

        answer, error = verifier.ask_with_retries(prompt)
        if error and not answer:
            tally.skipped += 1
            tally.errors.append(f"{candidate.rule_id}: {error}")
            print(f"{header}  SKIPPED after {MAX_ATTEMPTS} attempts — {error}", flush=True)
            log_result(
                {
                    "rule_id": candidate.rule_id,
                    "verdict": "SKIPPED",
                    "error": error,
                    "model": args.model,
                    "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                }
            )
            if i < len(candidates):
                time.sleep(args.sleep)
            continue

        verdict, reasoning = parse_verdict(answer)

        if args.dry_run:
            print("--- RAW API RESPONSE " + "-" * 75)
            print(answer)
            print()
            print("--- PARSED " + "-" * 85)
            print(f"  verdict   : {verdict}")
            print(f"  reasoning : {' '.join(reasoning.split())[:400]}")
            print(f"  effect    : {'verified=false -> true' if verdict == VERIFIED else 'verified stays false'}")
            print()
        else:
            mark = "OK " if verdict == VERIFIED else "-- "
            print(f"{header}  {mark}{verdict}", flush=True)

        if verdict == VERIFIED:
            tally.verified += 1
        else:
            tally.review += 1

        if not args.dry_run:
            apply_verdict(candidate, verdict, reasoning, args.model)
            # Fault tolerance: the file on disk is correct after every single rule.
            candidate.table.save()
            log_result(
                {
                    "rule_id": candidate.rule_id,
                    "kind": candidate.kind,
                    "verdict": verdict,
                    "reasoning": " ".join(reasoning.split()),
                    "claim": candidate.claim(),
                    "quote": candidate.row.get("quote", ""),
                    "model": args.model,
                    "effort": args.effort,
                    "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                }
            )

        if i < len(candidates):
            time.sleep(args.sleep)

    print()
    print("=" * 96)
    print("SUMMARY")
    print("=" * 96)
    print(f"  processed             : {len(candidates)}")
    print(f"  VERIFIED              : {tally.verified}")
    print(f"  NEEDS_HUMAN_REVIEW    : {tally.review}")
    print(f"  skipped (API errors)  : {tally.skipped}")
    if not args.dry_run:
        remaining = total_unverified - tally.verified
        print(f"  still unverified      : {remaining} of {total_unverified}")
        print(f"  audit log             : {AUDIT_LOG}")
    print(
        f"  tokens                : in {usage.input_tokens:,} "
        f"(cache read {usage.cache_read_tokens:,}, write {usage.cache_write_tokens:,}), "
        f"out {usage.output_tokens:,}"
        + (f" (+{usage.thinking_tokens:,} thinking)" if usage.thinking_tokens else "")
    )
    cost = usage.cost_usd(args.model)
    print(f"  approx. cost          : {f'${cost:.2f}' if cost is not None else 'n/a (no rate on file for this model)'}")
    if args.provider == "bedrock" and cost is not None:
        print("                          (Anthropic list price; AWS bills Bedrock at its own rate)")
    if tally.errors:
        print()
        print("  errors:")
        for line in tally.errors[:20]:
            print(f"    - {line}")
    print("=" * 96)
    if args.dry_run:
        print()
        print("Dry run: no CSV was written. Re-run without --dry-run to process the whole backlog.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
