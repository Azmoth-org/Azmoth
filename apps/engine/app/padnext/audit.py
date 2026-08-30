"""Check a PADnext delivery against the rules engine.

A PADnext file arrives already coded, so this is not the coding pipeline — it is the coding
pipeline run backwards. The claimed positions become the candidate set, the same Datalog program
decides which of them survive the GOÄ suppression rules, and the money is recomputed from our own
catalog and compared with what the file claims.

Three things this deliberately does:

**It refuses real patient data.** `auftrag/@echtdaten` distinguishes production from test data. This
project's ground rule is synthetic data only, so a delivery flagged as real data is rejected before
anything is parsed out of it, unless someone with a lawful basis sets
`PADNEXT_ALLOW_REAL_DATA=1`. Refusing is the safe default; a POC has no business holding real
billing records.

**It does not trust the file's arithmetic.** `gesamtbetrag` is recomputed and any difference is
reported to the cent. The spec is explicit that these fields exist *für Kontrollzwecke*, so
checking them is the intended use, not an imposition.

**It never silently drops a position.** Every claimed line comes back with a verdict, and every
verdict that is not `chargeable` carries a reason.

**It does not call a gap in its own rules a defect in someone's invoice.** The claimed total is
split into `confirmed_fine` / `confirmed_wrong` / `unconfirmed`, and the split turns on whether a
*verified* rule bore on the position — `rules_bearing_on` and `classify_position` below. A position
the solver did not confirm is `blocked` in the verdict but only `unconfirmed` in the money, because
"no verified rule kept it" is the absence of evidence. Getting this wrong is not a rounding problem:
a position no verified rule reaches is the common case rather than the exception, so a single "at
risk" figure computed by subtraction reports revenue as disputed when it was simply never checked.
The share varies with the rule set and the catalog, which is exactly why the report carries the
counts (`rule_coverage_detail`) instead of anything here quoting one.
"""

from __future__ import annotations

import os
import time
from collections.abc import Sequence
from decimal import Decimal

from app.bridge.entity_to_ziffer import BridgeResult
from app.catalog import Catalog
from app.config import Settings, get_settings
from app.errors import EngineError, ErrorCode
from app.padnext.schema import SCHEMA_VIOLATION_FINDING_TYPE
from app.schemas import (
    ClinicalAct,
    ClinicalExtraction,
    CodeCandidate,
    Conflict,
    JustificationFactor,
    Patient,
    Setting,
    Warning_,
)
from app.schemas.padnext import (
    BEHANDLUNGSART_LABEL,
    BEHANDLUNGSART_TO_SETTING,
    PadnextAuditedPosition,
    PadnextAuditReport,
    PadnextDelivery,
    PadnextFinding,
    PadnextPosition,
    PositionBucket,
)
from app.rules.rule_store import (
    ExclusionRule,
    FactorCapRule,
    Rule,
    RuleStore,
    SpecificityRule,
    ZielleistungRule,
)
from app.services import rule_coverage as rule_coverage_service
from app.services.receipt import receipt_hash
from app.validation.validator import cent_to_eur, line_amount_cent

#: § 6a Abs. 1 rates, as percentages, keyed by the setting our rules use.
SETTING_MINDERUNG_PERCENT: dict[Setting, Decimal] = {
    "ambulant": Decimal("0"),
    "stationaer": Decimal("25"),
    "belegarzt": Decimal("15"),
}


#: Engine warning types this module re-reports itself, with a position number and a recomputation
#: attached. Keeping both would show a reviewer one defect twice under two different names.
ENGINE_WARNINGS_REPORTED_PER_POSITION = frozenset(
    {
        "unknown_ziffer",
        "factor_above_hoechstsatz",
        # The Leistungslegende cap, for the same reason as the Höchstsatz above it: the audit now
        # re-reports it per position, with the position number and the cap that was broken, so the
        # engine's Ziffer-keyed copy would only be the same defect under a second name.
        "factor_above_leistungslegende_cap",
        "inactive_ziffer",
    }
)

#: Finding types that put a position in `confirmed_wrong` — the defects whose basis is something a
#: human has actually verified, so the conclusion survives a payer's challenge.
#:
#: What qualifies, and why each one is not merely advisory:
#:
#:   padnext_amount_mismatch        arithmetic. Punkte × Faktor × Punktwert, all three from the
#:                                 versioned, SHA-256-pinned catalog. No rule judgement involved.
#:   padnext_factor_above_maximum   § 5 Abs. 1 GOÄ. The bands in `factor_bands.csv` are verified.
#:   padnext_justification_missing  § 12 Abs. 3 GOÄ requires a written reason above the verified
#:                                 threshold factor, and the `begruendung` field is empty. The
#:                                 statute is the basis; nothing was inferred.
#:   padnext_inactive_ziffer        the catalog carries the Ziffer as not active. Catalog identity
#:                                 is pinned in the receipt, so this is checkable after the fact.
#:
#: What is deliberately absent is as important. `padnext_not_confirmed` is not here: "the rules did
#: not confirm this" is the *absence* of a verified rule, which is the definition of unconfirmed.
#: `padnext_unknown_ziffer` is not here either — a Ziffer missing from a catalog whose own coverage
#: is `partial` is a gap in our data, not proof the practice invented a service.
#: `padnext_no_faktor_or_einzelbetrag` is absent because an unpriceable line is one we could not
#: check, not one we checked and rejected. And the `*_mismatch` control-field findings are warnings
#: about inconsistent metadata, not about money — position 6 of the bundled example claims the wrong
#: `punktzahl` while its euros recompute to the cent.
VERIFIED_DEFECT_FINDINGS = frozenset(
    {
        "padnext_amount_mismatch",
        "padnext_factor_above_maximum",
        "padnext_justification_missing",
        "padnext_inactive_ziffer",
    }
)


class RealDataRefused(EngineError, RuntimeError):
    """The delivery says it holds production data, which this POC will not process.

    `422 REAL_DATA_REFUSED`, not `403`: nothing about the caller is being denied, and the file is
    perfectly readable — it is the *content* this deployment refuses to process. A client that saw
    a 403 would go looking for a permission to acquire; the fix is a lawful basis and the controls
    in `docs/compliance/PRIVATE_DATA_WARNING.md`, or a test file.
    """

    error_code = ErrorCode.REAL_DATA_REFUSED
    http_status = 422


class EchtdatenUndeclared(EngineError, RuntimeError):
    """The delivery never said whether it holds real patients, so it is refused.

    Three inputs land here and they are one situation: `@echtdaten` absent, `@echtdaten=""`, and
    `@echtdaten="ja"` — anything outside the `0`/`false`/`1`/`true` the specification defines.

    **Why this is a refusal and not a warning.** It used to be a warning: the reader mapped every
    unrecognised value to `False`, the audit noted "Es wurde von Testdaten ausgegangen" on the
    report, and the delivery was processed. Read that sequence again from the other end — a
    practice exports from a PVS that writes `echtdaten="ja"`, uploads real patients, and the
    system tells them it assumed they were fake. The assumption is load-bearing and the file is
    the only thing that could have justified it.

    The asymmetry decides it. Refusing an anonymised delivery that failed to say so costs one
    command and one re-upload. Accepting a real one costs an Art. 9 GDPR processing of health data
    with no lawful basis, § 203 StGB exposure for the practice, and a notification. A default is a
    guess about which of those to make when the file is silent, and there is only one defensible
    way to guess.

    `422`, same as `RealDataRefused` and for the same reason: the request is well formed and the
    *content* is refused. A separate `error_code`, because the client action is different —
    "your file did not declare itself, run the anonymiser" is a fixable export problem, and
    "you sent production data" is not.
    """

    error_code = ErrorCode.ECHTDATEN_UNDECLARED
    http_status = 422


def real_data_allowed(settings: Settings | None = None) -> bool:
    """Whether a delivery flagged as production data may be processed at all.

    The environment is consulted before settings on purpose: `get_settings()` is cached for the
    process lifetime, so an operator (or a test) flipping the variable must not need a restart to
    tighten it. Absent the variable, the configured default — `False` — applies.
    """
    raw = os.getenv("PADNEXT_ALLOW_REAL_DATA")
    if raw is not None and raw.strip():
        return raw.strip().lower() in {"1", "true", "yes"}
    return bool((settings or get_settings()).padnext_allow_real_data)


def _as_finding(warning: Warning_, *, positionsnr: str | None = None) -> PadnextFinding:
    return PadnextFinding(
        type=warning.type,
        severity=warning.severity,
        message=warning.message,
        ziffer=warning.ziffer,
        positionsnr=positionsnr,
        legal_basis=warning.legal_basis,
        rule_id=warning.rule_id,
    )


def _act_id(position: PadnextPosition, index: int) -> str:
    """Stable, collision-free id. positionsnr is only unique within a case, so the index leads."""
    return f"pad{index}"


def derive_setting(
    delivery: PadnextDelivery, findings: list[PadnextFinding]
) -> tuple[Setting, str]:
    """Work out the § 6a setting from behandlungsart, cross-checked against minderungssatz.

    Both are optional in a PADnext file and either can be wrong, so a disagreement is reported
    rather than resolved silently — the reduction is money, and guessing at it is how a practice
    ends up under-billing an entire quarter.
    """
    art = next(
        (c.behandlungsart for inv in delivery.invoices for c in inv.cases if c.behandlungsart),
        None,
    )
    rate = next(
        (
            c.minderungssatz
            for inv in delivery.invoices
            for c in inv.cases
            if c.minderungssatz is not None
        ),
        None,
    )

    setting: Setting = "ambulant"
    source = "default (keine behandlungsart angegeben)"

    if art is not None:
        if art in BEHANDLUNGSART_TO_SETTING:
            setting = BEHANDLUNGSART_TO_SETTING[art]
            source = f"behandlungsart={art} ({BEHANDLUNGSART_LABEL.get(art, art)})"
        else:
            findings.append(
                PadnextFinding(
                    type="padnext_behandlungsart_not_mapped",
                    severity="warning",
                    message=(
                        f"behandlungsart={art} ({BEHANDLUNGSART_LABEL.get(art, 'unbekannt')}) "
                        "lässt sich nicht eindeutig auf ambulant/stationär/belegärztlich "
                        "abbilden. Die Prüfung läuft als 'ambulant' — die Minderung nach § 6a "
                        "ist damit möglicherweise nicht berücksichtigt."
                    ),
                    legal_basis="§ 6a Abs. 1 GOÄ",
                )
            )
            source = f"behandlungsart={art}, nicht abbildbar → ambulant angenommen"
    elif rate is not None:
        # No behandlungsart, but a rate: infer the setting from the rate the file itself claims.
        for candidate, percent in SETTING_MINDERUNG_PERCENT.items():
            if percent == rate and percent != 0:
                setting = candidate
                source = f"minderungssatz={rate} % (behandlungsart fehlt)"
                break

    if rate is not None:
        expected = SETTING_MINDERUNG_PERCENT[setting]
        if rate != expected:
            findings.append(
                PadnextFinding(
                    type="padnext_minderung_mismatch",
                    severity="warning",
                    message=(
                        f"Die Datei nennt minderungssatz={rate} %, aus '{source}' folgt nach "
                        f"§ 6a Abs. 1 GOÄ aber {expected} %."
                    ),
                    legal_basis="§ 6a Abs. 1 GOÄ",
                    claimed=f"{rate} %",
                    recomputed=f"{expected} %",
                )
            )

    return setting, source


def build_audit_input(
    delivery: PadnextDelivery, setting: Setting
) -> tuple[ClinicalExtraction, BridgeResult, dict[str, Decimal], dict[str, PadnextPosition]]:
    """Turn claimed positions into the shape the rules engine already consumes.

    One synthetic act per claimed position, so a `begruendung` on a position can be bound to it as
    a § 12 Abs. 3 justification through the bridge's existing entity addressing.
    """
    bridge = BridgeResult()
    justifications: list[JustificationFactor] = []
    proposed_factors: dict[str, Decimal] = {}
    by_ziffer: dict[str, PadnextPosition] = {}

    for index, position in enumerate(delivery.positions(), start=1):
        if not position.is_goae:
            continue
        act_id = _act_id(position, index)
        bridge.acts.append(
            ClinicalAct(
                act_id=act_id,
                entity_id=act_id,
                source="procedure",
                entity_type=f"padnext_position_{position.ziffer}",
                description=position.text or f"PADnext Position {position.positionsnr}",
                confidence=Decimal("1"),
            )
        )
        bridge.candidates.append(
            CodeCandidate(
                act_id=act_id,
                ziffer=position.ziffer,
                priority=100,
                confidence=Decimal("1"),
                mapping_provenance="padnext_claimed",
                mapping_notes=f"positionsnr={position.positionsnr}",
            )
        )
        if position.faktor is not None:
            # Last one wins if a Ziffer appears twice; the duplicate is reported separately.
            proposed_factors[position.ziffer] = position.faktor
        if position.begruendung:
            justifications.append(
                JustificationFactor(
                    id=f"just_{act_id}",
                    reason=position.begruendung,
                    severity="schwer",
                    applies_to=[act_id],
                )
            )
        by_ziffer.setdefault(position.ziffer, position)

    extraction = ClinicalExtraction(
        patient=Patient(setting=setting),
        justification_factors=justifications,
        notes="Synthetisiert aus einer PADnext-Lieferung zur Prüfung. Keine Patientendaten.",
    )
    return extraction, bridge, proposed_factors, by_ziffer


def _recompute(
    position: PadnextPosition,
    catalog: Catalog,
    setting: Setting,
) -> tuple[Decimal | None, int | None]:
    """Recompute a line from our own catalog. Returns (eur, punkte)."""
    entry = catalog.get(position.ziffer)
    if entry is None or position.faktor is None:
        return None, (entry.punkte if entry else None)

    gross_cent = line_amount_cent(entry.punkte, position.faktor, catalog.punktwert_cent)

    # § 6a Abs. 1: the reduction applies unless the position is exempt (Buchstabe J).
    percent = position.minderungssatz
    if percent is None:
        percent = SETTING_MINDERUNG_PERCENT[setting]
    if percent and not catalog.minderung_exempt(position.ziffer):
        gross_cent = gross_cent * (Decimal("100") - percent) / Decimal("100")

    per_unit = cent_to_eur(gross_cent)
    return per_unit * position.anzahl, entry.punkte


# ------------------------------------------------------------------------------------------
# rule relevance — which rules actually bore on THIS invoice, and had a human checked them
# ------------------------------------------------------------------------------------------


def _rule_endpoints(rule: Rule) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """A rule's `(all Ziffern it names, the Ziffern it could suppress)`.

    Suppression direction follows `logic/datalog/goae_rules.dl` exactly, because a bucket that
    disagreed with the solver about which side of a rule loses would be worse than no bucket:

        exclusion(A, B)          if A is charged, B is not chargeable  → B loses
                                 (mutual: either could lose, so both do)
        zielleistung(P, C)       C is a component of P                → C loses
        specificity(S, G)        S displaces the more general G        → G loses
        factor_cap(Z, max)       caps Z's Steigerungsfaktor           → Z is constrained

    Analog candidates are absent by construction: § 6 Abs. 2 GOÄ makes them offers, never
    constraints, so one can neither confirm a position nor cast doubt on it.
    """
    if isinstance(rule, ExclusionRule):
        both = (rule.from_ziffer, rule.to_ziffer)
        return both, (both if rule.is_mutual else (rule.to_ziffer,))
    if isinstance(rule, ZielleistungRule):
        return (rule.parent_ziffer, rule.child_ziffer), (rule.child_ziffer,)
    if isinstance(rule, SpecificityRule):
        return (rule.specific_ziffer, rule.general_ziffer), (rule.general_ziffer,)
    if isinstance(rule, FactorCapRule):
        return (rule.ziffer,), (rule.ziffer,)
    return (), ()


def _constraint_rules(rules: RuleStore) -> list[Rule]:
    """Every rule that could constrain an invoice, enforced or held back by policy.

    `suppressed` has to be included and cannot be inferred from the others: under the default
    `warn` policy an unverified rule never reaches `exclusions`/`zielleistung`/… at all, so reading
    only the enforcement lists would find zero advisory rules and report every position as fully
    audited. That is precisely the overclaim these buckets exist to prevent.
    """
    return [
        *rules.exclusions,
        *rules.zielleistung,
        *rules.specificity,
        *rules.factor_caps,
        *rules.suppressed,
    ]


def rules_bearing_on(
    rules: RuleStore, claimed_ziffern: set[str]
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Split the rules that bear on this invoice into verified and advisory, keyed by Ziffer.

    Returns `(verified_by_ziffer, advisory_by_ziffer)`.

    Two filters, and both are load-bearing.

    **Relevance.** A rule bears on an invoice only if *every* Ziffer it names is claimed. An
    exclusion saying "Nr. 4 is not chargeable beside Nr. 30" tells us nothing about an invoice that
    charges neither, and counting it as coverage would inflate the audited share with rules that
    never ran. This is the same restriction `RuleStore.restrict_to` applies before grounding, so the
    buckets and the solver agree on what was in scope.

    **Attribution.** A *verified* rule is credited to both of its endpoints, because the solver
    evaluated it against both and each side got an answer — for `ziel_man_301_200`, that GOÄ 200 is
    a component and that GOÄ 301 is the Zielleistung that carries it. An *advisory* rule is charged
    only against the side it would have suppressed: an unenforced rule that would have removed
    GOÄ 200 leaves GOÄ 301's status untouched, and blaming both would make the unconfirmed bucket
    swallow positions nothing actually threatens.
    """
    verified: dict[str, list[str]] = {}
    advisory: dict[str, list[str]] = {}

    for rule in _constraint_rules(rules):
        named, loses = _rule_endpoints(rule)
        if not named or not set(named) <= claimed_ziffern:
            continue
        target, ziffern = (verified, named) if rule.verified else (advisory, loses)
        for ziffer in ziffern:
            bucket = target.setdefault(ziffer, [])
            if rule.rule_id and rule.rule_id not in bucket:
                bucket.append(rule.rule_id)

    return (
        {z: sorted(ids) for z, ids in verified.items()},
        {z: sorted(ids) for z, ids in advisory.items()},
    )


def mutual_exclusion_survivors(
    rows: Sequence[PadnextAuditedPosition], conflicts: Sequence[Conflict]
) -> set[int]:
    """The one position per mutual-exclusion cluster whose euros are *not* an overcharge.

    Returns the `id()` of each surviving row, matching how `blocking_rule_id` is keyed and for the
    same reason: `positionsnr` is unique only within an `abrechnungsfall`.

    A `Conflict` is an unordered pair the rules refused to decide between, because the invoice alone
    cannot say which service the practice actually performed. Both sides are correctly reported
    `blocked` — neither is confirmed billable, and the practice must drop one. What does not follow
    is that *both* amounts are wrong. Charging GOÄ 5 (10.72 €) beside GOÄ 7 (21.45 €) overcharges by
    at most 10.72 €; billing 32.17 € to `confirmed_wrong` claims the whole encounter was fictitious
    and overstates a provable finding by 3×.

    So each cluster keeps its most valuable member and every other member is the overcharge. Keeping
    the dearest is the reading most favourable to the practice, which is the only safe direction for
    a figure we intend to put in front of a payer: whatever the practice meant to keep, it cannot
    have been worth more than that, so the remainder is chargeable to `confirmed_wrong` no matter
    which way the ambiguity resolves. It is a lower bound on the overcharge, and it is stated as
    one.

    Clusters, not pairs. GOÄ 5/6/7/8 and 650–653 arrive as several overlapping pairs, and picking a
    survivor per pair would leave every member of a four-way cluster surviving something. The pairs
    are unioned into connected components first, so a cluster of four yields exactly one survivor
    and three overcharges.

    Ties break on `positionsnr` then `ziffer`, so two positions at the same price cannot make the
    result depend on dict ordering — the receipt hash covers this figure.
    """
    by_ziffer: dict[str, list[PadnextAuditedPosition]] = {}
    for row in rows:
        # Only rows the conflict branch actually blocked. A Ziffer that appears in a Conflict but
        # was suppressed by a *directed* rule as well is already attributed to that rule, and a
        # chargeable row is not in the cluster at all.
        if row.verdict == "blocked" and row.blocked_by:
            by_ziffer.setdefault(row.ziffer, []).append(row)

    # -- union the pairs into clusters --------------------------------------------------------
    parent: dict[str, str] = {}

    def find(z: str) -> str:
        parent.setdefault(z, z)
        while parent[z] != z:
            parent[z] = parent[parent[z]]
            z = parent[z]
        return z

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for conflict in conflicts:
        if conflict.ziffer_a in by_ziffer and conflict.ziffer_b in by_ziffer:
            union(conflict.ziffer_a, conflict.ziffer_b)

    clusters: dict[str, list[PadnextAuditedPosition]] = {}
    for ziffer in parent:
        clusters.setdefault(find(ziffer), []).extend(by_ziffer.get(ziffer, []))

    def value(row: PadnextAuditedPosition) -> tuple[Decimal, str, str]:
        # A position with no `gesamtbetrag` contributes nothing to any bucket, so it must never win
        # the cluster and take the survivor slot away from a priced position.
        return (
            row.claimed_amount_eur if row.claimed_amount_eur is not None else Decimal("-1"),
            row.positionsnr,
            row.ziffer,
        )

    survivors: set[int] = set()
    for members in clusters.values():
        if len(members) > 1:
            survivors.add(id(max(members, key=value)))
    return survivors


def classify_position(
    row: PadnextAuditedPosition,
    *,
    verified_defects: set[str],
    blocking_rule_verified: bool | None,
    mutual_exclusion_survivor: bool = False,
) -> tuple[PositionBucket, str]:
    """Put one audited position into one of the three buckets, and say why.

    `verified_defects` are the `VERIFIED_DEFECT_FINDINGS` raised against this position, and
    `blocking_rule_verified` is whether the rule that suppressed it has been human-verified —
    `None` when nothing suppressed it, or when the solver simply failed to confirm it and there is
    no rule to point at.

    The order of the tests is the argument. Proof that a position is wrong comes first and is not
    softened by advisory noise. Everything that follows is a reason we *cannot* speak, and only a
    position that survives all of them is called safe.
    """
    if verified_defects:
        return "confirmed_wrong", (
            "Verifizierte Prüfung fehlgeschlagen: " + ", ".join(sorted(verified_defects)) + "."
        )

    # Checked after `verified_defects` and before the blocked branch. After, because surviving the
    # cluster says nothing about the rest of the line: the dearest of two mutually exclusive
    # positions can still recompute to the wrong amount, and that defect is its own. Before, because
    # this is precisely the case where a verified rule fired and still cannot say which side loses.
    if row.verdict == "blocked" and mutual_exclusion_survivor:
        return "unconfirmed", (
            f"Wechselseitiger Ausschluss mit GOÄ {row.blocked_by}: eine der beiden Positionen ist "
            "berechnungsfähig, die Rechnung lässt aber offen welche. Als teurere Position wird "
            "diese nicht als Überzahlung gewertet — der Ausschluss ist gegen die günstigere "
            "gebucht. Welche Leistung tatsächlich erbracht wurde, muss ein Mensch entscheiden."
        )

    if row.verdict == "blocked" and blocking_rule_verified:
        return "confirmed_wrong", (
            f"Durch die verifizierte Regel '{row.blocked_by or 'Ausschluss'}' nicht "
            "berechnungsfähig."
        )

    if row.verdict == "out_of_scope":
        return "unconfirmed", (
            f"Gebührenordnung '{row.go}' wird nicht geprüft — keine Aussage möglich, kein Befund."
        )

    if row.verdict == "unknown_ziffer":
        return "unconfirmed", (
            "Ziffer ist in unserem Katalog nicht enthalten. Nicht nachrechenbar und nicht "
            "beurteilbar — das ist eine Lücke in unseren Daten, kein Nachweis eines Fehlers."
        )

    if row.verdict == "blocked":
        # The dishonest case this refactor exists for: the solver did not return the Ziffer as
        # billable and no rule says why. "Not confirmed" is the absence of evidence, so it must not
        # be counted as evidence of a defect.
        return "unconfirmed", (
            "Die Regelprüfung hat diese Ziffer nicht bestätigt, aber auch keine verifizierte Regel "
            "verletzt. Erfordert menschliche Prüfung."
        )

    if row.advisory_rule_ids:
        return "unconfirmed", (
            f"{len(row.advisory_rule_ids)} nicht verifizierte Regel(n) betreffen diese Ziffer und "
            "werden nach aktueller Policy nicht durchgesetzt: "
            f"{', '.join(row.advisory_rule_ids)}. Ob die Position zulässig ist, ist damit offen."
        )

    if not row.accepted_as_claimed:
        return "unconfirmed", (
            "Die Position hat eine Prüfung nicht bestanden, für die keine verifizierte Grundlage "
            "vorliegt. Erfordert menschliche Prüfung."
        )

    if not row.verified_rule_ids:
        return "unconfirmed", (
            "Keine verifizierte Regel bildet diese Ziffer ab. Die Position ist unauffällig, aber "
            "unbestätigt — das ist keine Freigabe."
        )

    return "confirmed_fine", (
        "Alle anwendbaren Prüfungen bestanden; geprüft gegen verifizierte Regel(n) "
        f"{', '.join(row.verified_rule_ids)}."
    )


def audit_delivery(
    delivery: PadnextDelivery,
    *,
    catalog: Catalog,
    rules: RuleStore,
    souffle_run,
    read_findings: list[Warning_] | None = None,
    settings: Settings | None = None,
) -> PadnextAuditReport:
    """Run the claimed positions through the rules engine and reconcile the money.

    `souffle_run(extraction, bridge, proposed_factors=...)` is injected rather than imported so
    this stays testable without a Soufflé binary, and so the caller controls engine construction.
    """
    started = time.perf_counter()
    settings = settings or get_settings()

    # ── The anonymisation gate. Nothing above this line reads a position. ──────────────────────
    #
    # Three-valued and closed on two of the three. `PADNEXT_ALLOW_REAL_DATA` opens both refusals
    # together and deliberately so: an operator who has established a lawful basis for processing
    # real deliveries has, a fortiori, accepted a delivery that merely failed to declare itself.
    # Two switches for one decision is a way to end up with the wrong one set.
    if not real_data_allowed(settings):
        if delivery.echtdaten is True:
            raise RealDataRefused(
                "Das Hochladen von Echtdaten ist im Pilotmodus nicht gestattet. Diese PADnext-"
                "Lieferung ist als Echtdaten gekennzeichnet (auftrag/@echtdaten). Bitte nutzen Sie "
                "das Azmoth-Anonymisierungsskript und laden Sie die Datei erneut hoch. "
                "— This PADnext delivery is flagged as production data (auftrag/@echtdaten). This "
                "deployment processes synthetic data only and has refused it. Set "
                "PADNEXT_ALLOW_REAL_DATA=1 only if you have a lawful basis and appropriate controls."
            )
        if delivery.echtdaten is None:
            # Quote the value back when there was one. "Das Feld ist ungültig" sends somebody to
            # search a 3 MB export for a field they cannot see; "es steht 'ja'" is a one-line fix
            # in the PVS export profile, and they can make it without opening the file.
            declared = (delivery.echtdaten_declared or "").strip()
            what = (
                f"Das Feld 'echtdaten' enthält den Wert '{declared}', der in der PADnext-"
                "Spezifikation nicht definiert ist (erlaubt sind '0'/'false' für Testdaten und "
                "'1'/'true' für Echtdaten)."
                if declared
                else "Das Feld 'echtdaten' fehlt oder ist ungültig."
            )
            raise EchtdatenUndeclared(
                f"{what} Diese Lieferung wird abgewiesen, weil ohne diese Angabe nicht "
                "feststellbar ist, ob sie echte Patientendaten enthält — und eine fehlende Angabe "
                "wird nicht als 'Testdaten' angenommen. Bitte nutzen Sie das "
                "Anonymisierungsskript (scripts/anonymize_padnext.py); es setzt echtdaten=\"false\" "
                "in der Auftragsdatei und in den Nutzdaten. "
                "— This delivery does not declare whether it holds production data. An undeclared "
                "delivery is refused rather than assumed to be synthetic. Run "
                "scripts/anonymize_padnext.py and upload its output, or fix the export to emit "
                "echtdaten=\"0\". Set PADNEXT_ALLOW_REAL_DATA=1 only with a lawful basis.",
                details={"echtdaten_declared": delivery.echtdaten_declared},
            )

    findings: list[PadnextFinding] = [_as_finding(w) for w in (read_findings or [])]

    if delivery.echtdaten is None:
        # Only reachable with PADNEXT_ALLOW_REAL_DATA=1 — the gate above refuses this otherwise.
        # `severity="warning"`, not `info`: on a deployment that has opened the door to real data,
        # a delivery that cannot say what it holds is the one most worth a second look, and the
        # old wording ("Es wurde von Testdaten ausgegangen") described an assumption this engine
        # no longer makes.
        findings.append(
            PadnextFinding(
                type="padnext_echtdaten_unknown",
                severity="warning",
                message=(
                    "Die Lieferung erklärt nicht, ob sie Echt- oder Testdaten enthält "
                    "(auftrag/@echtdaten fehlt oder ist ungültig). Sie wurde nur geprüft, weil "
                    "PADNEXT_ALLOW_REAL_DATA gesetzt ist; ohne diese Einstellung wird eine "
                    "Lieferung ohne Angabe abgewiesen."
                ),
            )
        )

    setting, setting_source = derive_setting(delivery, findings)
    extraction, bridge, proposed_factors, _ = build_audit_input(delivery, setting)

    claimed = delivery.positions()
    goae = [p for p in claimed if p.is_goae]

    seen: dict[str, str] = {}
    for position in goae:
        if position.ziffer in seen:
            findings.append(
                PadnextFinding(
                    type="padnext_duplicate_ziffer",
                    severity="warning",
                    positionsnr=position.positionsnr,
                    ziffer=position.ziffer,
                    message=(
                        f"GOÄ {position.ziffer} kommt mehrfach vor (Positionen "
                        f"{seen[position.ziffer]} und {position.positionsnr}). Die Regelprüfung "
                        "betrachtet eine Ziffer nur einmal; Mengenregeln sind nicht modelliert."
                    ),
                )
            )
        else:
            seen[position.ziffer] = position.positionsnr

    engine_started = time.perf_counter()
    rules_result = souffle_run(extraction, bridge, proposed_factors=proposed_factors) if goae else None
    solve_time_ms = round((time.perf_counter() - engine_started) * 1000, 2) if goae else 0.0

    billable: set[str] = set(rules_result.billable) if rules_result else set()
    blocked_by_ziffer = {b.ziffer: b for b in (rules_result.blocked if rules_result else [])}
    conflicts = list(rules_result.conflicts) if rules_result else []
    proof_by_ziffer: dict[str, list[str]] = {}
    for step in rules_result.proof if rules_result else []:
        proof_by_ziffer.setdefault(step.ziffer, []).append(step.rule)
    needs_justification = set(rules_result.factor_needs_justification if rules_result else [])
    factor_invalid = set(rules_result.factor_invalid if rules_result else [])

    # The engine reports some of the same defects, but keyed only by Ziffer. Where we re-report one
    # per position with the position number and the recomputation, the engine's copy is strictly
    # less useful — drop it rather than show a reviewer the same defect twice under two names.
    position_of_ziffer = {p.ziffer: p.positionsnr for p in goae}
    for warning in rules_result.warnings if rules_result else []:
        if warning.type in ENGINE_WARNINGS_REPORTED_PER_POSITION:
            continue
        findings.append(
            _as_finding(warning, positionsnr=position_of_ziffer.get(warning.ziffer or ""))
        )

    audited: list[PadnextAuditedPosition] = []
    claimed_total = Decimal("0.00")
    recomputed_total = Decimal("0.00")
    comparable_claimed = Decimal("0.00")
    unpriceable_claimed = Decimal("0.00")
    #: Rule id of whatever suppressed a position, keyed by `id()` of the audited row.
    #:
    #: Keyed by object identity rather than by `positionsnr`, which is only unique *within* an
    #: `abrechnungsfall` — a delivery with two cases can carry two positions numbered "1", and
    #: keying on that would let one case's verified exclusion push the other case's position into
    #: `confirmed_wrong`. The rows outlive this dict, so their ids are stable and distinct.
    #:
    #: Absent when nothing suppressed the position, and absent when the solver merely failed to
    #: confirm the Ziffer — that case has no rule to name, which is exactly what keeps it out of
    #: `confirmed_wrong`.
    blocking_rule_id: dict[int, str] = {}

    for position in claimed:
        entry = catalog.get(position.ziffer)
        row = PadnextAuditedPosition(
            positionsnr=position.positionsnr,
            ziffer=position.ziffer,
            go=position.go,
            is_analog=position.is_analog,
            in_catalog=entry is not None,
            official_text=entry.official_text if entry else "",
            claimed_faktor=position.faktor,
            claimed_amount_eur=position.gesamtbetrag,
            punkte=entry.punkte if entry else None,
        )

        if position.gesamtbetrag is not None:
            claimed_total += position.gesamtbetrag

        if not position.is_goae:
            row.verdict = "out_of_scope"
            row.reason = (
                f"Gebührenordnung '{position.go}' wird von diesem Proof of Concept nicht geprüft."
            )
            findings.append(
                PadnextFinding(
                    type="padnext_fee_schedule_out_of_scope",
                    severity="info",
                    positionsnr=position.positionsnr,
                    ziffer=position.ziffer,
                    message=row.reason,
                )
            )
            unpriceable_claimed += position.gesamtbetrag or Decimal("0.00")
            audited.append(row)
            continue

        if entry is None:
            row.verdict = "unknown_ziffer"
            row.reason = f"GOÄ {position.ziffer} ist im Katalog {catalog.catalog_version} nicht enthalten."
            findings.append(
                PadnextFinding(
                    type="padnext_unknown_ziffer",
                    severity="error",
                    positionsnr=position.positionsnr,
                    ziffer=position.ziffer,
                    message=row.reason,
                )
            )
            unpriceable_claimed += position.gesamtbetrag or Decimal("0.00")
            audited.append(row)
            continue

        if not entry.is_active:
            findings.append(
                PadnextFinding(
                    type="padnext_inactive_ziffer",
                    severity="error",
                    positionsnr=position.positionsnr,
                    ziffer=position.ziffer,
                    message=f"GOÄ {position.ziffer} ist im Katalog als '{entry.status}' geführt.",
                )
            )

        blocked = blocked_by_ziffer.get(position.ziffer)
        # A Conflict is an unordered pair (ziffer_a, ziffer_b) the rules refused to decide between.
        in_conflict = next(
            (c for c in conflicts if position.ziffer in (c.ziffer_a, c.ziffer_b)), None
        )

        if blocked is not None:
            row.verdict = "blocked"
            row.reason = blocked.explanation or blocked.detail or blocked.reason
            row.blocked_by = blocked.blocked_by
            row.legal_basis = blocked.legal_basis
            blocking_rule_id[id(row)] = blocked.rule_id
            findings.append(
                PadnextFinding(
                    type=f"padnext_blocked_{blocked.reason}",
                    severity="error",
                    positionsnr=position.positionsnr,
                    ziffer=position.ziffer,
                    message=(
                        f"GOÄ {position.ziffer} ist neben "
                        f"{'GOÄ ' + blocked.blocked_by if blocked.blocked_by else 'einer anderen Position'}"
                        f" nicht berechnungsfähig: {row.reason}"
                    ),
                    legal_basis=blocked.legal_basis,
                    rule_id=blocked.rule_id,
                )
            )
        elif position.ziffer in billable:
            row.verdict = "chargeable"
            row.proof = sorted(proof_by_ziffer.get(position.ziffer, []))
        elif in_conflict is not None:
            other = (
                in_conflict.ziffer_b
                if in_conflict.ziffer_a == position.ziffer
                else in_conflict.ziffer_a
            )
            row.verdict = "blocked"
            row.blocked_by = other
            blocking_rule_id[id(row)] = in_conflict.rule_id
            row.reason = (
                f"GOÄ {position.ziffer} und GOÄ {other} schließen sich gegenseitig aus. Die "
                "Rechnung enthält beide; nur eine davon ist berechnungsfähig."
            )
            findings.append(
                PadnextFinding(
                    type="padnext_mutual_exclusion",
                    severity="error",
                    positionsnr=position.positionsnr,
                    ziffer=position.ziffer,
                    message=row.reason,
                    legal_basis=in_conflict.legal_basis or "Leistungslegende GOÄ",
                    rule_id=in_conflict.rule_id,
                )
            )
        else:
            row.verdict = "blocked"
            row.reason = (
                "Die Regelprüfung hat diese Ziffer nicht als berechnungsfähig bestätigt. "
                "Es liegt keine spezifischere Begründung vor."
            )
            findings.append(
                PadnextFinding(
                    type="padnext_not_confirmed",
                    severity="warning",
                    positionsnr=position.positionsnr,
                    ziffer=position.ziffer,
                    message=row.reason,
                )
            )

        # -- factor band, § 5 / § 12 Abs. 3 ------------------------------------------------
        band = catalog.factor_band(position.ziffer)
        if position.faktor is not None:
            row.factor_within_band = position.faktor <= band.max
            row.legal_basis = row.legal_basis or band.legal_basis

            # § 12 Abs. 3 attaches to *every* factor above the Schwellenwert, and it does not stop
            # attaching when the factor also breaks the § 5 Höchstsatz — a line charged at 4.0 needs
            # a written reason and is illegal, not one instead of the other. Recorded before the
            # branch below because these two flags used to live inside the `elif`, where the cap
            # check short-circuited them and a 4.0 factor reported `justification_required: false`.
            # The *finding* below stays in the `elif`: a reviewer should see one error per line, and
            # "the factor is above the legal maximum" is the one that decides what happens next.
            if position.faktor > band.threshold:
                row.justification_required = True
                row.justification_present = bool(position.begruendung)

            # Two different ceilings end up in `factor_invalid`, and they are not interchangeable:
            # `invalid_factor` is the § 5 chapter band (3.5 in Abschnitt B), `invalid_factor_cap` is
            # a Leistungslegende cap from an Anmerkung ("nur mit dem einfachen Gebührensatz" → 1.0).
            # Reporting `band.max` for both produced a sentence that was simply untrue — GOÄ 52 at
            # 2.3 breaks its 1.0 cap and was reported as "Faktor 2.3 überschreitet den Höchstsatz
            # 3.5". That was unreachable while no factor cap was enforced; it stopped being
            # unreachable the moment the caps in `factor_caps.csv` were verified.
            cap = rules.factor_cap(position.ziffer)
            over_band = position.faktor > band.max
            over_cap = cap is not None and position.faktor > cap.max_factor
            if over_band or over_cap or position.ziffer in factor_invalid:
                # The band is the stricter statement about the fee schedule as a whole, so it wins
                # when both are broken; otherwise report whichever ceiling was actually exceeded.
                if over_band or not over_cap:
                    limit, basis, rule_id = band.max, band.legal_basis or "§ 5 Abs. 1 GOÄ", ""
                    message = (
                        f"Faktor {position.faktor} überschreitet den Höchstsatz {limit} "
                        f"für GOÄ {position.ziffer}."
                    )
                else:
                    limit, basis, rule_id = cap.max_factor, cap.legal_basis, cap.rule_id
                    message = (
                        f"Faktor {position.faktor} überschreitet den in der Leistungslegende "
                        f"festgelegten Höchstwert {limit} für GOÄ {position.ziffer}."
                    )
                findings.append(
                    PadnextFinding(
                        type="padnext_factor_above_maximum",
                        severity="error",
                        positionsnr=position.positionsnr,
                        ziffer=position.ziffer,
                        message=message,
                        legal_basis=basis or "§ 5 Abs. 1 GOÄ",
                        rule_id=rule_id,
                        claimed=str(position.faktor),
                        recomputed=f"max {limit}",
                    )
                )
            elif position.faktor > band.threshold:
                if not position.begruendung:
                    findings.append(
                        PadnextFinding(
                            type="padnext_justification_missing",
                            severity="error",
                            positionsnr=position.positionsnr,
                            ziffer=position.ziffer,
                            message=(
                                f"Faktor {position.faktor} liegt über dem Schwellenwert "
                                f"{band.threshold}. § 12 Abs. 3 GOÄ verlangt eine schriftliche "
                                "Begründung; das Feld 'begruendung' ist leer."
                            ),
                            legal_basis="§ 12 Abs. 3 GOÄ",
                            claimed=str(position.faktor),
                        )
                    )
        elif position.einzelbetrag is None:
            findings.append(
                PadnextFinding(
                    type="padnext_no_faktor_or_einzelbetrag",
                    severity="error",
                    positionsnr=position.positionsnr,
                    ziffer=position.ziffer,
                    message=(
                        "Position gibt weder faktor noch einzelbetrag an; der Betrag kann nicht "
                        "nachgerechnet werden."
                    ),
                )
            )

        if position.ziffer in needs_justification and not position.begruendung:
            row.justification_required = True

        # -- money -------------------------------------------------------------------------
        recomputed, _ = _recompute(position, catalog, setting)
        if recomputed is None:
            unpriceable_claimed += position.gesamtbetrag or Decimal("0.00")
        else:
            row.recomputed_amount_eur = recomputed
            recomputed_total += recomputed
            if position.gesamtbetrag is not None:
                comparable_claimed += position.gesamtbetrag
                delta = position.gesamtbetrag - recomputed
                row.amount_delta_eur = delta
                if delta != 0:
                    findings.append(
                        PadnextFinding(
                            type="padnext_amount_mismatch",
                            severity="error",
                            positionsnr=position.positionsnr,
                            ziffer=position.ziffer,
                            message=(
                                f"gesamtbetrag {position.gesamtbetrag} € weicht von der "
                                f"Nachrechnung {recomputed} € ab ({delta:+} €). Grundlage: "
                                f"{entry.punkte} Punkte × Faktor {position.faktor} × "
                                f"{catalog.punktwert_cent} ct."
                            ),
                            legal_basis="§ 5 Abs. 1 GOÄ",
                            claimed=f"{position.gesamtbetrag} €",
                            recomputed=f"{recomputed} €",
                        )
                    )

        if position.punktzahl is not None and position.punktzahl != entry.punkte:
            findings.append(
                PadnextFinding(
                    type="padnext_punktzahl_mismatch",
                    severity="warning",
                    positionsnr=position.positionsnr,
                    ziffer=position.ziffer,
                    message=(
                        f"punktzahl {position.punktzahl} weicht von der Katalog-Punktzahl "
                        f"{entry.punkte} für GOÄ {position.ziffer} ab."
                    ),
                    claimed=str(position.punktzahl),
                    recomputed=str(entry.punkte),
                )
            )

        if position.punktwert is not None and position.punktwert != catalog.punktwert_cent:
            findings.append(
                PadnextFinding(
                    type="padnext_punktwert_mismatch",
                    severity="warning",
                    positionsnr=position.positionsnr,
                    ziffer=position.ziffer,
                    message=(
                        f"punktwert {position.punktwert} weicht vom gesetzlichen Punktwert "
                        f"{catalog.punktwert_cent} ct ab."
                    ),
                    legal_basis="§ 5 Abs. 1 Satz 3 GOÄ",
                    claimed=str(position.punktwert),
                    recomputed=str(catalog.punktwert_cent),
                )
            )

        if position.is_analog:
            findings.append(
                PadnextFinding(
                    type="padnext_analog_needs_review",
                    severity="warning",
                    positionsnr=position.positionsnr,
                    ziffer=position.ziffer,
                    message=(
                        f"Position ist als Analogansatz zu GOÄ {position.analog_for} deklariert. "
                        "Ob die Gleichwertigkeit medizinisch trägt, ist eine ärztliche "
                        "Entscheidung und wird hier nicht geprüft."
                    ),
                    legal_basis="§ 6 Abs. 2 GOÄ",
                )
            )

        audited.append(row)

    # A line is billable as claimed only if the rules kept it AND nothing else about it is wrong.
    # Computing this after the loop is deliberate: an error finding can be raised about a position
    # after its verdict is set (an illegal factor, an amount that does not recompute), and a
    # single-pass version silently counted those euros as defensible.
    errors_per_position: dict[str, int] = {}
    #: positionsnr → the VERIFIED_DEFECT_FINDINGS raised against it. Collected in the same pass, so
    #: a defect can never be counted for `accepted_as_claimed` but missed for the buckets.
    #:
    #: Keyed by `positionsnr`, and therefore carrying the same pre-existing limitation as
    #: `errors_per_position` above: a `PadnextFinding` identifies its position only by that number,
    #: which is unique within an `abrechnungsfall` but not across a multi-case delivery. Two cases
    #: each numbering a position "1" would share both maps. De-colliding it means giving findings a
    #: delivery-unique position key, which is an API change and out of scope here — noted rather
    #: than silently inherited.
    verified_defects_per_position: dict[str, set[str]] = {}
    for finding in findings:
        if not finding.positionsnr:
            continue
        if finding.severity == "error":
            errors_per_position[finding.positionsnr] = (
                errors_per_position.get(finding.positionsnr, 0) + 1
            )
        if finding.type in VERIFIED_DEFECT_FINDINGS:
            verified_defects_per_position.setdefault(finding.positionsnr, set()).add(finding.type)

    defensible_total = Decimal("0.00")
    for row in audited:
        row.accepted_as_claimed = row.verdict == "chargeable" and not errors_per_position.get(
            row.positionsnr
        )
        if row.accepted_as_claimed and row.recomputed_amount_eur is not None:
            defensible_total += row.recomputed_amount_eur

    # -- the three honest buckets ----------------------------------------------------------
    #
    # Claimed euros, not recomputed ones, so the three add up to `claimed_total` exactly and the
    # reconciliation check on the report can be an equality rather than an estimate. Every position
    # contributes to exactly one bucket; a position with no `gesamtbetrag` contributes nothing to
    # any of them, and nothing to `claimed_total` either, so the identity still holds.
    verified_by_ziffer, advisory_by_ziffer = rules_bearing_on(
        rules, {p.ziffer for p in goae}
    )

    bucket_totals: dict[PositionBucket, Decimal] = {
        "confirmed_fine": Decimal("0.00"),
        "confirmed_wrong": Decimal("0.00"),
        "unconfirmed": Decimal("0.00"),
    }
    #: One survivor per mutual-exclusion cluster, so a cluster costs the invoice its cheaper
    #: members and not the whole cluster. See `mutual_exclusion_survivors`.
    survivors = mutual_exclusion_survivors(audited, conflicts)

    for row in audited:
        # Out-of-scope positions carry a Ziffer from another fee schedule, whose numbers collide
        # with GOÄ ones — GOZ 2020 is not GOÄ 2020. Looking up rules for them would attribute GOÄ
        # rules to a dental position, so they get no rules and fall through to `unconfirmed`.
        if row.verdict != "out_of_scope":
            row.verified_rule_ids = verified_by_ziffer.get(row.ziffer, [])
            row.advisory_rule_ids = advisory_by_ziffer.get(row.ziffer, [])

        blocked_rule = blocking_rule_id.get(id(row))
        rule = rules.rule_by_id(blocked_rule) if blocked_rule else None
        # Under the default `warn` policy an unverified rule never reaches the enforcement path, so
        # anything that actually blocked is verified. Under `block` it can be unverified, and then
        # the suppression is real but the basis is not — `None` keeps it out of `confirmed_wrong`.
        blocking_rule_verified = rule.verified if rule is not None else None

        row.bucket, row.bucket_reason = classify_position(
            row,
            verified_defects=verified_defects_per_position.get(row.positionsnr, set()),
            blocking_rule_verified=blocking_rule_verified,
            mutual_exclusion_survivor=id(row) in survivors,
        )
        bucket_totals[row.bucket] += row.claimed_amount_eur or Decimal("0.00")

    judged = bucket_totals["confirmed_fine"] + bucket_totals["confirmed_wrong"]
    # An invoice claiming nothing was not "0 % audited" in any meaningful sense, but reporting 1.0
    # would let an empty delivery render as fully verified. Zero is the reading that cannot mislead.
    coverage_ratio = float(judged / claimed_total) if claimed_total else 0.0

    coverage = rule_coverage_service.build(
        rules,
        rule_coverage=catalog.rule_coverage,
        rules_version=catalog.rules_version,
    )
    findings.extend(
        PadnextFinding(type=w.type, severity=w.severity, message=w.message)
        for w in rule_coverage_service.warnings_for(coverage)
    )

    receipt = receipt_hash(
        catalog_version=catalog.catalog_version,
        catalog_sha256=catalog.sha256(),
        rules_version=catalog.rules_version,
        rules_hash=rule_coverage_service.rules_hash(settings.rules_data_dir),
        logic_version=settings.logic_version,
        solver_version=settings.clingo_version,
        policy=settings.policy_fingerprint(),
        facts=[p.model_dump(mode="python") for p in claimed],
        output=[r.model_dump(mode="python") for r in audited],
    )

    return PadnextAuditReport(
        source_name=delivery.source_name,
        nachrichtentyp=delivery.nachrichtentyp,
        echtdaten=delivery.echtdaten,
        setting=setting,
        setting_source=setting_source,
        positions=audited,
        findings=findings,
        schema_warnings=[
            f.message for f in findings if f.type == SCHEMA_VIOLATION_FINDING_TYPE
        ],
        schema_policy=delivery.schema_policy or str(settings.padnext_schema_policy),
        claimed_total_eur=claimed_total,
        recomputed_total_eur=recomputed_total,
        comparable_claimed_eur=comparable_claimed,
        arithmetic_delta_eur=comparable_claimed - recomputed_total,
        defensible_total_eur=defensible_total,
        unpriceable_claimed_eur=unpriceable_claimed,
        confirmed_fine_eur=bucket_totals["confirmed_fine"],
        confirmed_wrong_eur=bucket_totals["confirmed_wrong"],
        unconfirmed_eur=bucket_totals["unconfirmed"],
        coverage_ratio=coverage_ratio,
        catalog_version=catalog.catalog_version,
        catalog_sha256=catalog.sha256(),  # a method, unlike its neighbours, which are properties
        rules_version=catalog.rules_version,
        logic_version=settings.logic_version,
        enforced_rule_count=coverage.enforced_rule_count,
        advisory_rule_count=coverage.advisory_rule_count,
        suppressed_unverified_rule_count=coverage.suppressed_unverified_rule_count,
        rule_coverage_detail=coverage,
        solve_time_ms=solve_time_ms,
        total_time_ms=round((time.perf_counter() - started) * 1000, 2),
        receipt_hash=receipt,
    )
