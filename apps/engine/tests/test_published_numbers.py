"""No shipped text may quote a rule count that the engine does not actually compute.

**Why this file exists.** The product's whole claim is that its conclusions are checkable. It
shipped, for weeks, a customer-facing PDF asserting that most extracted exclusion rules were still
unconfirmed and therefore not applied — long after verification had promoted almost all of them —
and an OpenAPI description and a partner contract quoting counts that were wrong by an order of
magnitude in the *other* direction. Nothing failed. Every one of those numbers had been true when
it was written, and a number written into prose is a claim with no mechanism to stay true.

So this is the same kind of guard as `test_error_handling.py`'s check that every `ErrorCode` has a
row in `docs/errors.md`: a documentation-drift test that turns a silent falsehood into a red build.

**What it enforces**, and the two halves are different on purpose:

1. **Code and prose may not quote a count at all.** `app/**/*.py`, the READMEs and the architecture
   docs must describe the *shape* of the rule set ("most rules were machine-extracted"), never its
   size. A qualitative sentence cannot go stale; a figure inevitably does, and the module that owns
   the figures (`app.services.rule_coverage`) is one HTTP call away for anyone who needs one.

2. **A worked example may quote one, and it must be right.** `docs/api/PARTNER_API.md` shows a real
   response so an integrator can check their own against it, and the marketing site's home page
   claims a rule count and a catalogue coverage share in its own headline copy. Deleting the numbers
   from either would make it useless — an integrator cannot check a response against nothing, and a
   marketing page whose whole pitch is "we do not assert what we cannot prove" cannot decline to say
   what it covers. So instead both are pinned to what the engine computes and this test fails the
   moment they diverge, which is what makes it safe to print them at all.

   The marketing site funnels every such figure through one module, `apps/marketing/src/lib/
   engine-facts.ts`, and keeps the German copy in `messages/de.json` free of digits by interpolating
   ICU placeholders. That is what makes the pinning possible: there is exactly one file to check.

**What is deliberately exempt, and why that is not a loophole.** `docs/audit/` and `docs/migration/`
are dated records of what was true at a moment. Rewriting them to match today would be falsifying
an audit trail — the precise opposite of what those documents are for. They are excluded by path,
with this reason attached, rather than by an inline marker somebody could sprinkle elsewhere.
"""

from __future__ import annotations

import json
import re

import pytest

from app.config import CATALOG_PATH, REPO_ROOT
from app.rules.rule_store import load_rules
from app.services.pipeline import Pipeline

#: Files that record history and must not be edited to match the present.
#:
#: Paths, not markers. A per-line "this number is historical" comment would be an exemption anyone
#: could apply to a live document, which is how a guard like this stops guarding anything.
HISTORICAL = (
    "docs/audit/",
    "docs/migration/",
)

#: Where a count must never appear, because nothing can keep it true.
#:
#: The engine's own source and the documents a reader treats as current. Tests are excluded — this
#: file quotes figures itself — and so is the rule data, which *is* the count.
SCANNED_GLOBS = (
    "apps/engine/app/**/*.py",
    "apps/web/app/**/*.tsx",
    "apps/web/components/**/*.tsx",
    #: The marketing site: its pages, its components, and the German copy they render.
    #: `src/lib/` is *not* scanned — `engine-facts.ts` is the one file allowed to hold
    #: these numbers, and it is pinned to the engine by its own test below.
    "apps/marketing/src/app/**/*.tsx",
    "apps/marketing/src/components/**/*.tsx",
    "apps/marketing/messages/*.json",
    "apps/engine/README.md",
    "README.md",
    "CONTRIBUTING.md",
    "docs/architecture/*.md",
    "docs/errors.md",
    "docs/DATA_HANDLING_POLICY.md",
)

#: The document allowed to quote live figures, checked against the engine below.
WORKED_EXAMPLE = REPO_ROOT / "docs" / "api" / "PARTNER_API.md"

#: The marketing site's single source for every engine figure it prints, checked below.
MARKETING_FACTS = REPO_ROOT / "apps" / "marketing" / "src" / "lib" / "engine-facts.ts"

#: Vocabulary that turns a bare integer into a claim about the rule set.
#:
#: Deliberately narrow. A three-digit number is usually a page size, a byte limit, an HTTP status or
#: a year, and a test that flagged all of them would be turned off within a week. What is being
#: caught is specifically "N rules", "N of M constraint rules", "N Regeln", "N exclusion rules".
RULE_WORDS = r"(?:constraint\s+)?(?:exclusion\s+)?(?:rules?|Regeln|Ausschlussregeln)"

#: `858 rules`, `859 of 894 constraint rules`, `837 der 869 Ausschlussregeln`, `35/894`.
COUNT_PATTERNS = (
    re.compile(rf"\b(\d{{2,4}})\s+(?:of|von|der)\s+\d{{2,4}}\s+{RULE_WORDS}\b", re.I),
    re.compile(rf"\b(\d{{2,4}})\s+{RULE_WORDS}\b", re.I),
    re.compile(rf"{RULE_WORDS}[^.\n]{{0,24}}?\b(\d{{2,4}})\s*/\s*(\d{{2,4}})\b", re.I),
)

#: Numbers small enough to be a quantity in an example rather than a claim about the corpus.
#:
#: "one of the 3 analog candidates" or "2 rules fired on this position" are statements about a
#: case, not about the rule table. The threshold is two digits because the smallest thing this
#: guard cares about — an enforced-rule count — has never been below ten.
IGNORE_BELOW = 10


def _shipped_files() -> list:
    seen: set = set()
    for pattern in SCANNED_GLOBS:
        for path in sorted(REPO_ROOT.glob(pattern)):
            if not path.is_file():
                continue
            relative = path.relative_to(REPO_ROOT).as_posix()
            if any(relative.startswith(prefix) for prefix in HISTORICAL):
                continue
            seen.add(path)
    return sorted(seen)


def _offences(text: str) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        for pattern in COUNT_PATTERNS:
            for match in pattern.finditer(line):
                if any(int(group) >= IGNORE_BELOW for group in match.groups() if group):
                    found.append((number, match.group(0).strip()))
    return found


def test_no_shipped_file_quotes_a_rule_count():
    """The guard. A count in prose is a claim nothing can keep true — so there are none.

    If this fails on a sentence you have just written, the fix is not to adjust the number: it is
    to describe the shape instead ("most rules were machine-extracted") and point at
    `GET /api/v1/rules/coverage`, which is computed and therefore cannot be wrong.
    """
    offences: dict[str, list[tuple[int, str]]] = {}
    for path in _shipped_files():
        hits = _offences(path.read_text(encoding="utf-8"))
        if hits:
            offences[path.relative_to(REPO_ROOT).as_posix()] = hits

    assert offences == {}, (
        "shipped text quotes a rule count, which will go stale and has before:\n"
        + "\n".join(
            f"  {path}:{line}  {snippet!r}"
            for path, hits in sorted(offences.items())
            for line, snippet in hits
        )
        + "\n\nDescribe the shape rather than the size, and point at GET /api/v1/rules/coverage."
    )


def test_the_worked_example_in_the_partner_contract_matches_the_engine():
    """The one document allowed to print figures, pinned to what the engine actually computes.

    An integrator checks their first response against this example, so the numbers have to be real.
    Real and unguarded is how the previous ones ended up wrong by 15×, so they are guarded here —
    which is the trade that makes printing them defensible at all.
    """
    if not WORKED_EXAMPLE.is_file():  # pragma: no cover - source checkouts always have it
        pytest.skip("docs/api/PARTNER_API.md is not present (running from a built image)")

    coverage = Pipeline().rule_coverage()
    text = WORKED_EXAMPLE.read_text(encoding="utf-8")

    for field, actual in (
        ("enforced_rule_count", coverage.enforced_rule_count),
        ("advisory_rule_count", coverage.advisory_rule_count),
    ):
        printed = re.search(rf'"{field}":\s*(\d+)', text)
        assert printed is not None, f"{field} is no longer in the worked example"
        assert int(printed.group(1)) == actual, (
            f"docs/api/PARTNER_API.md prints {field} = {printed.group(1)}, the engine computes "
            f"{actual}. The example is what a partner checks their first response against — "
            "update it, or remove the field from the example."
        )


def test_the_pdf_caveat_counts_rather_than_asserts():
    """The sentence that reaches a payer must be derived, not written.

    Asserted against the module rather than a rendered document because the failure being guarded
    is somebody replacing the computed sentence with a fixed one — which is exactly what was there
    before, and which no assertion about a *rendered* PDF would notice until the figures next moved.

    The source comes from the imported module rather than from a path built on `REPO_ROOT`. In a
    checkout the two agree; in the container image they do not — the app is installed at `/srv/app`
    and `REPO_ROOT` resolves to `/srv`, so `REPO_ROOT / "apps/engine/app/services/pdf.py"` names a
    file that does not exist and this test could never pass where CI actually runs it. Asking the
    module object where it came from is also the stronger assertion: it reads the code that was
    imported, not a file we hope is the same one.
    """
    import inspect

    from app.services import pdf

    source = inspect.getsource(pdf)

    assert hasattr(pdf, "_coverage_sentence"), (
        "the PDF's coverage caveat must be computed from the report; see _coverage_sentence"
    )
    assert "_coverage_sentence(job, summary)" in source, (
        "render_batch_report no longer builds its caveat from the report's own counts"
    )
    for stale in ("Grossteil", "Großteil"):
        assert stale not in source, (
            f"the PDF caveat says {stale!r} — an unquantified claim about how much of the rule set "
            "is unverified. That sentence was false for weeks. State the counted figures instead."
        )


def test_the_marketing_site_quotes_the_engine_and_not_a_memory():
    """The public home page prints a rule count and a catalogue share. Both are pinned here.

    This is the same trade as the partner contract above, made for a louder audience. The site's
    argument is that Azmoth states only what it can prove, and it makes that argument concrete by
    naming the share of the GOÄ catalogue no enforced rule speaks to. A page that made that claim
    from a number somebody typed in once would be refuting itself in its own headline.

    So the four figures live in one TypeScript module with no prose around them, the German copy
    interpolates them as ICU placeholders, and this test reads them back out. Change a rule set
    without changing that module and the engine's own suite goes red.

    The two derived percentages — "96 %" enforced, "16,3 %" of the catalogue — are deliberately not
    checked, because they are not written down: `engine-facts.ts` computes them from the counts
    below with `Intl.NumberFormat`. There is nothing there to drift.
    """
    if not MARKETING_FACTS.is_file():  # pragma: no cover - source checkouts always have it
        pytest.skip("apps/marketing is not present (running from a built image)")

    store = load_rules()
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))

    #: Every Ziffer named by a rule that may actually suppress a position. The marketing site
    #: divides this by the catalog size to state its coverage, so it is computed the same way
    #: here rather than being a second constant nobody would remember to update.
    under_rule: set[str] = set()
    for rule in store.exclusions:
        under_rule.update((rule.from_ziffer, rule.to_ziffer))
    for rule in store.zielleistung:
        under_rule.update((rule.parent_ziffer, rule.child_ziffer))
    for rule in store.specificity:
        under_rule.update((rule.specific_ziffer, rule.general_ziffer))
    for rule in store.factor_caps:
        under_rule.add(rule.ziffer)
    under_rule.discard("")

    text = MARKETING_FACTS.read_text(encoding="utf-8")

    for constant, actual in (
        ("ENFORCED_RULE_COUNT", store.enforced_rule_count()),
        ("CONSTRAINT_RULE_COUNT", store.constraint_rule_count()),
        ("CATALOG_ZIFFER_COUNT", len(catalog["ziffern"])),
        ("ZIFFERN_UNDER_RULE_COUNT", len(under_rule)),
    ):
        printed = re.search(rf"export const {constant} = (\d+);", text)
        assert printed is not None, (
            f"{constant} is no longer exported from apps/marketing/src/lib/engine-facts.ts. "
            "The marketing copy interpolates it; removing it silently drops the figure from a "
            "public page rather than correcting it."
        )
        assert int(printed.group(1)) == actual, (
            f"engine-facts.ts publishes {constant} = {printed.group(1)}, the engine computes "
            f"{actual}. That number is rendered on azmoth.com — update the module."
        )
