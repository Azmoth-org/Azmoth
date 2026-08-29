#!/usr/bin/env python3
"""Operations CLI — the engine without the HTTP layer.

    python scripts/engine_cli.py check                 # engines, data, logic, end-to-end probe
    python scripts/engine_cli.py check-souffle         # can the rules engine actually evaluate?
    python scripts/engine_cli.py solve <case.json>     # code one case
    python scripts/engine_cli.py solve <case.json> --stats   # ... with a timing breakdown
    python scripts/engine_cli.py padnext <file.padx>   # audit a delivery
    python scripts/engine_cli.py catalog --ziffer 301  # provenance, or one position

`check` is what the Docker build runs: it fails the image if the shipped catalog, rule tables or
logic programs cannot actually drive a coding run. Catching that at build time is much cheaper than
catching it in front of a user.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE_ROOT))

from pydantic import ValidationError  # noqa: E402


def _print_json(payload) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))


def _load_extraction(path: Path):
    """Accept either a bare extraction or a `{"extraction": {...}}` envelope."""
    from app.schemas import ClinicalExtraction

    payload = json.loads(path.read_text(encoding="utf-8"))
    if "extraction" in payload and isinstance(payload["extraction"], dict):
        payload = payload["extraction"]
    return ClinicalExtraction.model_validate(payload)


# ==========================================================================================
# check
# ==========================================================================================


def cmd_check(args: argparse.Namespace) -> int:
    """Verify the whole stack is usable: engines, data, logic, facts, schema."""
    ok = True
    lines: list[str] = []

    def report(name: str, passed: bool, detail: str = "") -> None:
        nonlocal ok
        ok = ok and passed
        lines.append(f"  [{'PASS' if passed else 'FAIL'}] {name}{f' — {detail}' if detail else ''}")

    from app.config import get_settings

    settings = get_settings()
    lines.append(f"app_env                : {settings.app_env}")
    lines.append(f"extraction_mode        : {settings.extraction_mode}")
    lines.append(f"unverified_rule_policy : {settings.unverified_rule_policy}")
    lines.append(f"base_factor_policy     : {settings.base_factor_policy}")
    lines.append(f"solver_timeout_seconds : {settings.solver_timeout_seconds}")
    lines.append(f"logic_dir              : {settings.logic_dir}")
    lines.append(f"data_dir               : {settings.data_dir}")
    lines.append("")

    # -- Soufflé --------------------------------------------------------------------------
    engine = None
    try:
        from app.solvers.souffle_engine import SouffleEngine

        engine = SouffleEngine()
        report("souffle available", engine.available(), engine.version() or "not on PATH")
    except Exception as exc:  # noqa: BLE001
        report("souffle available", False, str(exc))

    # -- Clingo ---------------------------------------------------------------------------
    try:
        import clingo

        report("clingo available", True, clingo.__version__)
    except Exception as exc:  # noqa: BLE001
        report("clingo available", False, str(exc))

    # -- logic programs -------------------------------------------------------------------
    report("datalog program present", settings.datalog_path.is_file(), str(settings.datalog_path))
    report("asp program present", settings.asp_path.is_file(), str(settings.asp_path))
    report("logic version resolvable", len(settings.logic_version) == 64, settings.logic_version[:16])

    # -- catalog --------------------------------------------------------------------------
    catalog = None
    try:
        from app.catalog import load_catalog

        catalog = load_catalog(settings.catalog_path)
        report(
            "catalog loads",
            True,
            f"{len(catalog.ziffern)} Ziffern, {catalog.catalog_version}, "
            f"coverage={catalog.rule_coverage}",
        )
        report(
            "catalog has factor bands",
            bool(catalog.factor_bands),
            f"{len(catalog.factor_bands)} bands",
        )
        report(
            "punktwert is Decimal",
            str(catalog.punktwert_cent) == "5.82873",
            str(catalog.punktwert_cent),
        )
        if settings.catalog_version:
            report(
                "catalog matches CATALOG_VERSION",
                settings.catalog_version == catalog.catalog_version,
                f"expected {settings.catalog_version}",
            )
    except Exception as exc:  # noqa: BLE001
        report("catalog loads", False, str(exc))

    # -- PADnext framing schema ------------------------------------------------------------
    #
    # Compiled here, at deploy time, because a schema that does not compile is a deployment fault
    # that would otherwise surface as a 500 on the first delivery someone uploads. CI runs this
    # command against the built image, so a broken or missing XSD fails the build instead.
    try:
        from app.padnext.schema import load_schema
        from lxml import etree

        xsd = settings.padnext_xsd_path
        load_schema(xsd)
        official = xsd.name != "padx_adl_v2.12.subset.xsd"
        report(
            "padnext schema compiles",
            True,
            f"{xsd.name} ({'licensed official' if official else 'bundled subset'}), "
            f"policy={settings.padnext_schema_policy}, libxml2 "
            f"{'.'.join(map(str, etree.LIBXML_VERSION))}",
        )

        example = settings.cases_dir / "padnext" / "00004711_20260726_ADL_000001_padx.xml"
        if example.is_file():
            from app.padnext.schema import validate_payload

            violations = validate_payload(example.read_bytes())
            report(
                "bundled PADnext example validates",
                not violations,
                f"{len(violations)} violation(s)"
                + (f": {violations[0].location}" if violations else ""),
            )
    except Exception as exc:  # noqa: BLE001
        report("padnext schema compiles", False, str(exc))

    # -- rules ----------------------------------------------------------------------------
    rules = None
    try:
        from app.rules.rule_store import RuleStore

        rules = RuleStore.load(settings.rules_data_dir, policy=settings.unverified_rule_policy)
        summary = rules.summary()
        report(
            "rules load",
            bool(rules.files_loaded),
            # `enforced_rules`, not `exclusions_enforced`: this line and the "rule coverage
            # reported" line below are read together, and quoting the exclusion subset here made
            # them disagree ("30 enforced" against "35 enforced") about the same rule store.
            f"{summary['enforced_rules']} of {summary['total_constraint_rules']} enforced, "
            f"{summary['unverified_rules_not_enforced']} unverified/not enforced",
        )
    except Exception as exc:  # noqa: BLE001
        report("rules load", False, str(exc))

    # -- rules reference only known Ziffern ------------------------------------------------
    if catalog and rules:
        dangling = [
            r.rule_id
            for r in rules.exclusions
            if not catalog.has(r.from_ziffer) or not catalog.has(r.to_ziffer)
        ]
        report("enforced rules reference known Ziffern", not dangling, f"{len(dangling)} dangling")

    # -- mapping --------------------------------------------------------------------------
    if catalog:
        try:
            from app.bridge.entity_to_ziffer import load_mapping

            mapping = load_mapping()
            unknown = sorted({r.ziffer for r in mapping if not catalog.has(r.ziffer)})
            report("mapping loads", bool(mapping), f"{len(mapping)} rows")
            report(
                "mapping references known Ziffern",
                not unknown,
                f"unknown: {unknown}" if unknown else "all present",
            )
        except Exception as exc:  # noqa: BLE001
            report("mapping loads", False, str(exc))

    # -- end to end -----------------------------------------------------------------------
    if catalog and rules and engine and engine.available():
        try:
            from app.schemas import ClinicalExtraction
            from app.services.pipeline import Pipeline

            pipeline = Pipeline(settings, catalog, rules)
            probe = ClinicalExtraction.model_validate(
                {
                    "patient": {"setting": "ambulant"},
                    "consultation": {"type": "beratung"},
                    "procedures": [{"type": "punktion", "organ": "knie"}],
                }
            )
            bridge = pipeline.bridge(probe)
            report(
                "facts generate", bool(bridge.candidates), f"{len(bridge.candidates)} candidates"
            )
            proposal = pipeline.propose(probe)
            report(
                "end-to-end coding",
                bool(proposal.solver_result.coding.proposed_codes),
                f"{[l.ziffer for l in proposal.solver_result.coding.proposed_codes]} "
                f"= {proposal.solver_result.coding.total.amount_eur} EUR",
            )
            report("result is a DRAFT proposal", str(proposal.status) == "DRAFT", str(proposal.status))
            report("receipt hash produced", len(proposal.receipt_hash) == 64, proposal.receipt_hash[:16])
            report(
                "rule coverage reported",
                proposal.enforced_rule_count > 0 and proposal.advisory_rule_count > 0,
                f"{proposal.enforced_rule_count} enforced / "
                f"{proposal.advisory_rule_count} advisory",
            )
        except Exception as exc:  # noqa: BLE001
            report("end-to-end coding", False, f"{type(exc).__name__}: {exc}")

    # -- API schema ------------------------------------------------------------------------
    try:
        from app.main import app

        schema = app.openapi()
        report(
            "openapi schema builds",
            bool(schema.get("paths")),
            f"{len(schema.get('paths', {}))} paths, "
            f"{len(schema.get('components', {}).get('schemas', {}))} schemas",
        )
    except Exception as exc:  # noqa: BLE001
        report("openapi schema builds", False, str(exc))

    print("\n".join(lines))
    print()
    print("check:", "OK" if ok else "FAILED")
    return 0 if ok else 1


def cmd_check_souffle(args: argparse.Namespace) -> int:
    """Just the rules engine, for a container healthcheck."""
    import subprocess
    import tempfile

    from app.solvers.souffle_engine import SouffleEngine

    engine = SouffleEngine()
    if not engine.available():
        print(
            f"souffle NOT FOUND (looked for '{engine.settings.souffle_bin}' on PATH)",
            file=sys.stderr,
        )
        return 1
    print(f"souffle {engine.version() or 'present'} at {engine.binary}")

    # Prove it can actually evaluate, not merely that the binary exists. Soufflé shells out to a
    # C preprocessor, so a missing mcpp makes a present binary useless.
    with tempfile.TemporaryDirectory() as tmp:
        program = Path(tmp) / "smoke.dl"
        program.write_text(".decl t(x:number)\nt(1).\n.output t\n", encoding="utf-8")
        proc = subprocess.run(
            [engine.settings.souffle_bin, "-D", tmp, str(program)],
            capture_output=True,
            text=True,
            timeout=30,
        )
    if proc.returncode != 0:
        print(f"souffle present but cannot evaluate:\n{proc.stderr}", file=sys.stderr)
        return 1
    print("souffle evaluates a trivial program: OK")
    return 0


# ==========================================================================================
# solve
# ==========================================================================================


def _print_stats(
    *,
    startup_ms: float,
    parse_ms: float,
    request_ms: float,
    proposal,
    grounding,
    catalog,
    rules,
) -> None:
    """The timing breakdown behind `--stats`, written to stdout.

    Read the three groups separately. **Startup** is paid once per process and not per case — the
    catalog and rule loaders are `lru_cache`d, so a long-running service pays it at boot and an API
    request pays none of it. **Per case** is what a request actually costs. **Ground program** is
    the size of what Clingo searched, and it is the number to watch: search time is a function of
    it, and it grows with the positions in play rather than with the encoding.
    """
    audit = proposal.solver_result.audit_trail
    stages = audit.stage_timings_ms
    #: Everything this case cost after startup: parsing, the symbolic pipeline, and the proposal
    #: work around it (receipt hash, cache write, rule-coverage build). Used as the denominator so
    #: the shares add to 100 % rather than to "100 % of the part someone remembered to time".
    #:
    #: `request_ms` is measured here rather than read off the proposal, because the payload's
    #: `total_time_ms` deliberately reports the *run* — a cache hit repeats the timings of the run
    #: it serves. The difference between the two is the proposal work, which is what `wrap_ms`
    #: names.
    per_case = parse_ms + request_ms
    wrap_ms = round(request_ms - audit.total_time_ms, 2)

    def row(label: str, ms: float, of: float | None = None) -> str:
        share = f"{ms / of * 100:>5.1f} %" if of else "       "
        return f"  {label:<34}{ms:>9.2f} ms  {share}"

    print()
    print("=" * 78)
    print(f"TIMING — {proposal.proposal_id}   catalog {proposal.catalog_version}")
    print("=" * 78)
    print("startup (once per process, cached thereafter)")
    print(row("catalog + rules load", startup_ms))
    print(
        f"       {len(catalog.ziffern)} Ziffern, {rules.summary()['exclusions_enforced']} enforced "
        f"exclusion rules"
    )
    print()
    print("per case")
    print(row("input parse + schema validation", parse_ms, per_case))
    print(row("bridge (entity -> Ziffer)", stages.get("bridge", 0.0), per_case))
    print(row("souffle (rules)", stages.get("souffle", 0.0), per_case))
    print(row("clingo build facts", stages.get("clingo_build_facts", 0.0), per_case))
    print(row("clingo ground", stages.get("clingo_ground", 0.0), per_case))
    print(row("clingo solve", stages.get("clingo_solve", 0.0), per_case))
    print(row("souffle (verification pass)", stages.get("souffle_verification", 0.0), per_case))
    print(row("validation + pricing", stages.get("validation", 0.0), per_case))
    print(row("receipt + cache + coverage", wrap_ms, per_case))
    print("  " + "-" * 52)
    print(row("solve_time_ms (payload)", proposal.solve_time_ms, per_case))
    print(row("total_time_ms (payload, pipeline)", proposal.total_time_ms, per_case))
    print(row("TOTAL end-to-end (incl. parse)", per_case, per_case))
    if proposal.cached:
        print("  (served from cache — the payload timings describe the run that filled it)")
    print()
    if grounding is None:
        # Not a failure: the numbers below are read from `clingo.Control.statistics`, and the
        # engine deliberately treats a missing or renamed key as "no diagnostics", never as a
        # failed solve. Fall back to reading the timing deltas above.
        print("ground program: clingo reported no statistics for this run")
    else:
        print("ground program (clingo statistics)")
        print(f"  {'atoms':<34}{grounding.atoms:>9}  ({grounding.atoms_aux} auxiliary)")
        print(f"  {'rules':<34}{grounding.rules:>9}  ({grounding.rules_choice} choice, "
              f"{grounding.rules_minimize} minimize)")
        print(f"  {'bodies':<34}{grounding.bodies:>9}")
        print(f"  {'injected fact lines':<34}{grounding.fact_lines:>9}")
        print(f"  {'program size':<34}{grounding.program_bytes:>9}  bytes")
        print(f"  {'search: choices / conflicts':<34}{grounding.choices:>9} / "
              f"{grounding.conflicts}")
    print("=" * 78)


def cmd_solve(args: argparse.Namespace) -> int:
    from app.services.pipeline import Pipeline
    from app.validation.validator import ValidationFailed

    path = Path(args.case)
    if not path.exists():
        print(f"error: {path} does not exist", file=sys.stderr)
        return 2

    # Startup and parsing are timed around the imports' side effects deliberately: the catalog and
    # the rule tables are loaded by `Pipeline()`, and pretending that cost belongs to the solve
    # would make every measurement here useless for capacity planning.
    startup_started = time.perf_counter()
    pipeline = Pipeline()
    startup_ms = round((time.perf_counter() - startup_started) * 1000, 2)

    parse_started = time.perf_counter()
    try:
        extraction = _load_extraction(path)
    except ValidationError as exc:
        print("error: the extraction JSON does not match the schema\n", file=sys.stderr)
        print(exc, file=sys.stderr)
        return 2
    parse_ms = round((time.perf_counter() - parse_started) * 1000, 2)

    request_started = time.perf_counter()
    try:
        proposal = pipeline.propose(extraction, setting=args.setting)
    except ValidationFailed as exc:
        _print_json(
            {"error": "validation_failed", "violations": [v.model_dump() for v in exc.violations]}
        )
        return 1
    request_ms = round((time.perf_counter() - request_started) * 1000, 2)

    # Read off the solver rather than the response: the ground-program size is a diagnostic about
    # how the answer was computed, not part of the answer, so it is deliberately not in the
    # payload a client receives.
    grounding = pipeline.clingo.last_grounding

    if args.json:
        _print_json(proposal.model_dump(mode="json"))
        if args.stats:
            _print_stats(
                startup_ms=startup_ms,
                parse_ms=parse_ms,
                request_ms=request_ms,
                proposal=proposal,
                grounding=grounding,
                catalog=pipeline.catalog,
                rules=pipeline.rules,
            )
        return 0

    response = proposal.solver_result
    coding = response.coding
    print(
        f"proposal {proposal.proposal_id}  status={proposal.status}  "
        f"receipt={proposal.receipt_hash[:16]}…"
    )
    print(
        f"catalog {response.audit_trail.catalog_version}  "
        f"rule_coverage={response.audit_trail.rule_coverage}  "
        f"rules={proposal.enforced_rule_count} enforced / {proposal.advisory_rule_count} advisory"
    )
    print()
    print(f"{'GOÄ':>6}  {'Punkte':>6}  {'Faktor':>6}  {'Betrag':>10}  Leistung")
    for line in coding.proposed_codes:
        flag = " [analog]" if line.is_analog else ""
        print(
            f"{line.ziffer:>6}  {line.punkte:>6}  {str(line.factor):>6}  "
            f"{str(line.amount_eur):>10}  {line.official_text[:52]}{flag}"
        )
    print(f"{'':>6}  {coding.total.punkte:>6}  {'':>6}  {str(coding.total.amount_eur):>10}  GESAMT")
    if coding.total.minderung_applied:
        print(f"        (§ 6a Minderung {coding.total.minderung_rate} angewendet)")
    print()
    for blocked in coding.blocked_codes:
        print(
            f"  GESPERRT {blocked.ziffer:>6}  {blocked.reason:<15} "
            f"{blocked.detail:<20} {blocked.rule_id}"
        )
    print()
    for gap in coding.missing_documentation:
        print(
            f"  DOKU     {gap.ziffer:>6}  Faktor {gap.current_factor} von möglichen "
            f"{gap.possible_factor} — {gap.missing[:80]}"
        )
    print()
    for warning in coding.warnings:
        print(f"  [{warning.severity:<7}] {warning.type}: {warning.message[:110]}")
    print()
    print("Dies ist ein VORSCHLAG (DRAFT), keine Rechnung. Ärztliche Prüfung erforderlich.")
    if args.stats:
        _print_stats(
            startup_ms=startup_ms,
            parse_ms=parse_ms,
            request_ms=request_ms,
            proposal=proposal,
            grounding=grounding,
            catalog=pipeline.catalog,
            rules=pipeline.rules,
        )
    return 0


def cmd_padnext(args: argparse.Namespace) -> int:
    """Audit a PADnext delivery: what the file charges, versus what the rules allow."""
    from app.padnext import PadnextError, RealDataRefused, audit_delivery, read_file
    from app.services.pipeline import Pipeline

    try:
        delivery, read_findings = read_file(args.file)
    except PadnextError as exc:
        # Caught here rather than left to `main`'s catalog handler so the exit code stays 2, which
        # is what this command has always returned for an unusable file. The code and the location
        # are printed alongside the message so the CLI says as much as the API does.
        print(f"error [{exc.error_code}]: {exc}", file=sys.stderr)
        if exc.details.get("location"):
            print(f"       at {exc.details['location']}", file=sys.stderr)
        return 2

    pipe = Pipeline()
    try:
        report = audit_delivery(
            delivery,
            catalog=pipe.catalog,
            rules=pipe.rules,
            souffle_run=pipe.souffle.run,
            read_findings=read_findings,
            settings=pipe.settings,
        )
    except RealDataRefused as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2

    if args.json:
        _print_json(report.model_dump(mode="json"))
        return 1 if report.has_errors else 0

    counts = report.summary()
    print(
        f"{report.source_name or args.file}  Nachrichtentyp={report.nachrichtentyp or '?'}  "
        f"Setting={report.setting} ({report.setting_source})"
    )
    print(f"catalog {report.catalog_version}  receipt={report.receipt_hash[:16]}…")
    print()
    print(
        f"{'Pos':>4}  {'GO':<4} {'Ziffer':>7}  {'Faktor':>6}  {'berechnet':>10}  "
        f"{'nachgerechnet':>13}  Bewertung / Urteil"
    )
    #: Red / green / grey, in the one form a terminal can be relied on to render.
    bucket_mark = {"confirmed_wrong": "!! ", "confirmed_fine": "OK ", "unconfirmed": "?? "}
    for row in report.positions:
        print(
            f"{row.positionsnr:>4}  {row.go:<4} {row.ziffer:>7}  "
            f"{str(row.claimed_faktor or '-'):>6}  "
            f"{str(row.claimed_amount_eur or '-'):>10}  "
            f"{str(row.recomputed_amount_eur or '-'):>13}  "
            f"{bucket_mark[row.bucket]}{row.bucket:<16} {row.verdict}"
        )
    print()
    buckets = report.bucket_summary()
    print(f"  berechnet insgesamt   {report.claimed_total_eur:>10} EUR")
    print(
        f"  bestätigt korrekt     {report.confirmed_fine_eur:>10} EUR  "
        f"({buckets['confirmed_fine']} von {len(report.positions)} Positionen, gegen "
        "verifizierte Regeln geprüft)"
    )
    print(
        f"  nachweislich falsch   {report.confirmed_wrong_eur:>10} EUR  "
        f"({buckets['confirmed_wrong']} Positionen — verifizierte Regel verletzt)"
    )
    print(
        f"  unbestätigt           {report.unconfirmed_eur:>10} EUR  "
        f"({buckets['unconfirmed']} Positionen — keine verifizierte Regel, KEIN Befund)"
    )
    print(
        f"  Prüfabdeckung         {report.coverage_ratio * 100:>9.1f} %  "
        "(Anteil der berechneten Summe, zu dem eine Aussage möglich war)"
    )
    print(
        f"  davon belegbar        {report.defensible_total_eur:>10} EUR  "
        f"(nachgerechnet, {counts['chargeable']} Positionen regelkonform)"
    )
    if report.arithmetic_delta_eur:
        print(
            f"  Rechenfehler          {report.arithmetic_delta_eur:>10} EUR  "
            "(nur nachrechenbare Positionen)"
        )
    if report.unpriceable_claimed_eur:
        print(
            f"  nicht nachrechenbar   {report.unpriceable_claimed_eur:>10} EUR  "
            f"({counts['unknown_ziffer']} unbekannt, {counts['out_of_scope']} andere GO)"
        )
    print()
    for finding in report.findings:
        where = f"Pos {finding.positionsnr}" if finding.positionsnr else "Lieferung"
        basis = f"  [{finding.legal_basis}]" if finding.legal_basis else ""
        print(f"  [{finding.severity:<7}] {where:<12} {finding.message}{basis}")

    return 1 if report.has_errors else 0


def cmd_catalog(args: argparse.Namespace) -> int:
    from app.catalog import load_catalog

    catalog = load_catalog()
    if args.ziffer:
        entry = catalog.get(args.ziffer)
        if entry is None:
            print(f"GOÄ {args.ziffer} not in catalog {catalog.catalog_version}", file=sys.stderr)
            return 1
        band = catalog.factor_band(args.ziffer)
        _print_json(
            {
                **entry.__dict__,
                "factor_band": {
                    "threshold": str(band.threshold),
                    "max": str(band.max),
                    "legal_basis": band.legal_basis,
                },
            }
        )
        return 0
    _print_json(catalog.summary())
    return 0


# ==========================================================================================


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="engine_cli",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("check", help="verify engines, data, logic and pipeline").set_defaults(
        func=cmd_check
    )
    sub.add_parser("check-souffle", help="verify the rules engine can evaluate").set_defaults(
        func=cmd_check_souffle
    )

    solve = sub.add_parser("solve", help="code one extraction JSON file")
    solve.add_argument("case", help="path to a clinical extraction JSON file")
    solve.add_argument("--setting", choices=["ambulant", "stationaer", "belegarzt"], default=None)
    solve.add_argument("--json", action="store_true", help="emit the full proposal as JSON")
    solve.add_argument(
        "--stats",
        action="store_true",
        help="print a timing breakdown: catalog load, parse, grounding, solve, total",
    )
    solve.set_defaults(func=cmd_solve)

    pad = sub.add_parser(
        "padnext", help="audit a PADnext delivery (.padx or *_padx.xml) against the GOÄ rules"
    )
    pad.add_argument("file", help="path to a .padx container or a *_padx.xml payload")
    pad.add_argument("--json", action="store_true", help="full report as JSON")
    pad.set_defaults(func=cmd_padnext)

    cat = sub.add_parser("catalog", help="catalog provenance, or one Ziffer")
    cat.add_argument("--ziffer", default=None)
    cat.set_defaults(func=cmd_catalog)

    args = parser.parse_args(argv)

    from app.errors import EngineError

    try:
        return args.func(args)
    except EngineError as exc:
        # The same catalog the API answers with, printed rather than served. A traceback would be
        # the wrong output for "this delivery is not well-formed XML at line 12" — the operator
        # running this needs the code, the message and the details, and `docs/errors.md` explains
        # every one of them. Exit 1 for a client-side problem, 2 for an engine-side one, so a shell
        # script can tell "fix your file" from "the engine is broken".
        print(json.dumps(exc.envelope(), indent=2, ensure_ascii=False), file=sys.stderr)
        return 1 if exc.http_status < 500 else 2


if __name__ == "__main__":
    raise SystemExit(main())
