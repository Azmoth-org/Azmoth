#!/usr/bin/env python3
"""Machine verification pass over the auto-extracted GOÄ rule tables.

    python scripts/auto_verify_rules.py --dry-run        # first 5 rules, prompts + verdicts, no writes
    python scripts/auto_verify_rules.py                  # the whole backlog, saving after every rule
    python scripts/auto_verify_rules.py --only exclusions --limit 50
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

DEFAULT_MODEL = "claude-opus-5"
DEFAULT_EFFORT = "high"
DEFAULT_SLEEP_SECONDS = 2.5
MAX_ATTEMPTS = 3
MAX_TOKENS = 4000

# Published rates, $/1M tokens, for the cost estimate only.
PRICING = {
    "claude-opus-5": (5.0, 25.0),
    "claude-fable-5": (10.0, 50.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-haiku-4-5": (1.0, 5.0),
}


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

    def add(self, usage) -> None:
        self.input_tokens += getattr(usage, "input_tokens", 0) or 0
        self.output_tokens += getattr(usage, "output_tokens", 0) or 0
        self.cache_read_tokens += getattr(usage, "cache_read_input_tokens", 0) or 0
        self.cache_write_tokens += getattr(usage, "cache_creation_input_tokens", 0) or 0

    def cost_usd(self, model: str) -> float:
        rate_in, rate_out = PRICING.get(model, (0.0, 0.0))
        billable_in = self.input_tokens + self.cache_write_tokens * 1.25 + self.cache_read_tokens * 0.1
        return (billable_in * rate_in + self.output_tokens * rate_out) / 1_000_000


class Verifier:
    """One Messages API call per rule, with bounded retries around the transient failures."""

    def __init__(self, model: str, effort: str, *, usage: Usage) -> None:
        import anthropic  # imported here so --help works without the SDK installed

        self._anthropic = anthropic
        # `max_retries=0`: the retry policy is ours, so that a skip is logged as a skip rather
        # than disappearing into the SDK's backoff.
        self.client = anthropic.Anthropic(max_retries=0, timeout=120.0)
        self.model = model
        self.effort = effort
        self.usage = usage

    def ask(self, user_prompt: str) -> str:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=MAX_TOKENS,
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    # The system prompt is byte-identical on all 859 calls; caching it is free
                    # money if it clears the model's minimum cacheable prefix.
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            # Adaptive thinking: this is a legal-reasoning task where a wrong VERIFIED is expensive.
            thinking={"type": "adaptive"},
            output_config={"effort": self.effort},
            messages=[{"role": "user", "content": user_prompt}],
        )
        self.usage.add(response.usage)
        if response.stop_reason == "refusal":
            detail = getattr(response, "stop_details", None)
            return f"VERDICT: {NEEDS_REVIEW}\nREASONING: the model declined to answer ({detail})."
        return "".join(b.text for b in response.content if b.type == "text").strip()

    def ask_with_retries(self, user_prompt: str) -> tuple[str, str | None]:
        """Returns (answer_text, error). On terminal failure the answer is an empty string."""
        a = self._anthropic
        last = ""
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                return self.ask(user_prompt), None
            except (a.BadRequestError, a.AuthenticationError, a.PermissionDeniedError, a.NotFoundError) as exc:
                # Nothing about a retry would change these — a bad model id or a rejected key
                # fails identically three times.
                return "", f"{type(exc).__name__}: {exc}"
            except a.RateLimitError as exc:
                wait = float(exc.response.headers.get("retry-after", "30") or 30)
                last = f"RateLimitError: {exc}"
            except (a.APIStatusError, a.APIConnectionError, a.APITimeoutError) as exc:
                wait = 2.0 * attempt
                last = f"{type(exc).__name__}: {exc}"
            if attempt < MAX_ATTEMPTS:
                print(f"      ! {last} — retry {attempt}/{MAX_ATTEMPTS - 1} in {wait:.0f}s", flush=True)
                time.sleep(wait)
        return "", last


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
# main
# ----------------------------------------------------------------------------------------------


@dataclass
class Tally:
    verified: int = 0
    review: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)


def _has_credentials() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


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
    parser.add_argument("--limit", type=int, default=0, help="stop after N rules (0 = all)")
    parser.add_argument(
        "--only",
        choices=("exclusions", "factor_caps"),
        help="restrict to one table (default: both)",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"default {DEFAULT_MODEL}")
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
    candidates = collect_candidates(tables, redo=args.redo)
    total_unverified = sum(
        1 for t in tables for r in t.rows if not _truthy(r.get("verified"))
    )

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
    print(f"  model / effort : {args.model} / {args.effort}")
    print(f"  mode           : {'DRY RUN — nothing will be written' if args.dry_run else 'LIVE — CSV saved after every rule'}")
    print("=" * 96)
    print()

    if not candidates:
        print("Nothing to do: every rule already carries a verdict or is verified.")
        return 0

    if not _has_credentials():
        print("!! No ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN in the environment.")
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
    verifier = Verifier(args.model, args.effort, usage=usage)
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
    )
    print(f"  approx. cost          : ${usage.cost_usd(args.model):.2f}")
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
