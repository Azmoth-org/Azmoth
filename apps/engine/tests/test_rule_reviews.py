"""The rule verification workflow: the merge, the counts, and the three endpoints.

What is being guarded is one claim with money behind it: **verifying a machine-extracted rule must
make it enforce exactly like a hand-curated one, and must therefore shrink the `unconfirmed` bucket
of every later audit.** If the merge silently did nothing, the review dashboard would still count
up, a reviewer would work through hundreds of rules, and no invoice would be audited any differently.
That failure is invisible from the outside, so it is tested from both ends: the pure merge on its
own, and an end-to-end assertion that a real PADnext audit moves euros after a review.

The merge half needs no database and no Soufflé — `RuleStore.with_reviews` takes a plain mapping,
which is the whole reason it was built that way.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.config import RULES_DATA_DIR, UnverifiedRulePolicy
from app.rules.rule_store import RuleReviewStatus, RuleStore
from app.services import rule_coverage as coverage_service
from app.services.rule_reviews import effective_rules_hash

# ==========================================================================================
# the merge, on its own
# ==========================================================================================


@pytest.fixture(scope="module")
def csv_rules() -> RuleStore:
    """The store exactly as the CSVs produce it, with no reviews applied."""
    return RuleStore.load(RULES_DATA_DIR, UnverifiedRulePolicy.WARN)


@pytest.fixture(scope="module")
def unverified_ids(csv_rules) -> list[str]:
    ids = [r.rule_id for r in csv_rules.suppressed]
    assert len(ids) > 3, "the fixtures must carry unverified rules or none of this means anything"
    return ids


def test_a_verified_review_turns_an_unverified_csv_rule_into_an_enforced_one(
    csv_rules, unverified_ids
):
    """The central claim. A rule the CSV marks `verified=false` becomes enforced after a review."""
    target = unverified_ids[0]
    assert csv_rules.rule_by_id(target).verified is False
    assert target not in {r.rule_id for r in csv_rules.exclusions}

    merged = csv_rules.with_reviews({target: RuleReviewStatus.VERIFIED})
    rule = merged.rule_by_id(target)

    assert rule.verified is True, "the effective flag must flip, or nothing downstream changes"
    assert rule.csv_verified is False, "and the CSV's own claim must still be readable"
    assert rule.review_status == "VERIFIED"
    assert target in {r.rule_id for r in merged.exclusions}, "it has to reach the enforcement list"
    assert target not in {r.rule_id for r in merged.suppressed}


def test_the_original_store_is_not_mutated_by_a_merge(csv_rules, unverified_ids):
    """`with_reviews` returns a new store. The pipeline hands its store to three engines at
    construction, so one that changed underneath them would make the three disagree."""
    before = len(csv_rules.exclusions)

    csv_rules.with_reviews({unverified_ids[0]: RuleReviewStatus.VERIFIED})

    assert len(csv_rules.exclusions) == before
    assert csv_rules.rule_by_id(unverified_ids[0]).verified is False


def test_a_rejected_review_keeps_the_rule_out_and_is_not_a_coverage_gap(csv_rules, unverified_ids):
    target = unverified_ids[1]

    merged = csv_rules.with_reviews({target: RuleReviewStatus.REJECTED})
    rule = merged.rule_by_id(target)

    assert rule.verified is False
    assert rule.rejected is True
    assert target not in {r.rule_id for r in merged.exclusions}
    assert target in {r.rule_id for r in merged.suppressed}
    assert merged.rejected_rule_count() == 1


def test_a_rejected_rule_is_refused_even_under_the_block_policy():
    """The one place rejection is stronger than "unverified".

    `UNVERIFIED_RULE_POLICY=block` enforces rules nobody has looked at. A rule somebody looked at
    and refused is the opposite of that, and enforcing it would let a policy switch resurrect a
    rule a billing expert had explicitly thrown out.
    """
    blocking = RuleStore.load(RULES_DATA_DIR, UnverifiedRulePolicy.BLOCK)
    target = next(r.rule_id for r in blocking.exclusions if not r.csv_verified)

    merged = blocking.with_reviews({target: RuleReviewStatus.REJECTED})

    assert target not in {r.rule_id for r in merged.exclusions}
    assert merged.rule_by_id(target).rejected is True


def test_pending_decides_nothing(csv_rules, unverified_ids):
    """A parked rule is still an unchecked rule, and the counts must say so."""
    target = unverified_ids[2]
    before = csv_rules.unverified_constraint_rule_count()

    merged = csv_rules.with_reviews({target: RuleReviewStatus.PENDING})

    assert merged.rule_by_id(target).verified is False
    assert merged.unverified_constraint_rule_count() == before
    assert merged.rejected_rule_count() == 0


def test_a_review_for_an_unknown_rule_id_is_ignored(csv_rules):
    """A review can outlive the rule it names — there is no foreign key and cannot be one."""
    merged = csv_rules.with_reviews({"excl_auto_this_rule_never_existed": "VERIFIED"})

    assert merged.summary() == csv_rules.summary()


def test_the_coverage_counts_move_with_the_reviews(csv_rules, unverified_ids):
    """Verified up, unverified down, and the total constant. The dashboard's whole arithmetic."""
    before = coverage_service.build(csv_rules)

    merged = csv_rules.with_reviews(
        {
            unverified_ids[0]: RuleReviewStatus.VERIFIED,
            unverified_ids[1]: RuleReviewStatus.VERIFIED,
            unverified_ids[2]: RuleReviewStatus.REJECTED,
        }
    )
    after = coverage_service.build(merged)

    assert after.enforced_rule_count == before.enforced_rule_count + 2
    assert after.review_verified_rule_count == 2
    assert after.rejected_rule_count == 1
    # Three rules decided, so the undecided pile drops by three — a rejection is a decision.
    assert after.unverified_rule_count == before.unverified_rule_count - 3
    # The denominator is a property of the CSVs and must not move because somebody reviewed.
    assert after.total_constraint_rule_count == before.total_constraint_rule_count


def test_the_denominator_is_the_number_the_dashboard_counts_towards(csv_rules):
    """894 as shipped: every constraint rule, excluding Analogansatz candidates.

    A candidate is an offer under § 6 Abs. 2 GOÄ and can never remove a position, so putting one in
    the queue would pad a reviewer's backlog with work that changes no outcome.
    """
    coverage = coverage_service.build(csv_rules)
    every_loaded_rule = (
        len(csv_rules.exclusions)
        + len(csv_rules.zielleistung)
        + len(csv_rules.specificity)
        + len(csv_rules.factor_caps)
        + len(csv_rules.suppressed)
        # Verified, but asserting an edge a hand-curated rule already covers, so held out of the
        # enforcement list. Still a rule the engine loaded, so still in the denominator: dropping it
        # would make the total shrink every time a machine pass rediscovers a manual rule.
        + len(csv_rules.redundant)
    )

    assert coverage.total_constraint_rule_count == every_loaded_rule
    assert coverage.total_constraint_rule_count == 894
    # Derived, not pinned. The *denominator* is a property of the CSVs and is asserted literally
    # above; the number still outstanding is supposed to fall as rules get verified, so a literal
    # here would have to be edited after every verification pass — which is exactly the kind of
    # edit that stops anyone reading what the test is for.
    assert coverage.unverified_rule_count == (
        coverage.total_constraint_rule_count
        - coverage.enforced_rule_count
        - len(csv_rules.redundant)
    )
    # The analog candidates are outside the denominator entirely.
    assert csv_rules.analog_candidates
    assert coverage.analog_candidate_count == len(csv_rules.analog_candidates)


def test_reviews_do_not_touch_the_csv_files(csv_rules, unverified_ids, tmp_path):
    """The constraint that made this feature a database table instead of a file writer."""
    before = {p.name: p.read_bytes() for p in RULES_DATA_DIR.glob("*.csv")}

    csv_rules.with_reviews({rule_id: RuleReviewStatus.VERIFIED for rule_id in unverified_ids[:5]})

    after = {p.name: p.read_bytes() for p in RULES_DATA_DIR.glob("*.csv")}
    assert before == after


# ------------------------------------------------------------------------------------------
# the rules identity
# ------------------------------------------------------------------------------------------


def test_no_reviews_leaves_the_rules_hash_byte_identical():
    """The property that keeps every existing golden receipt valid.

    `rules_hash` feeds the receipt hash and the cache key, so a deployment that has never used the
    review queue has to hash exactly as it did before this feature existed.
    """
    assert effective_rules_hash("abc123", {}) == "abc123"
    assert effective_rules_hash("abc123", {"r1": "PENDING"}) == "abc123"


def test_a_decided_review_moves_the_rules_hash():
    """It must. Otherwise two proposals with one receipt hash could describe different rule sets,
    and the cache would serve an answer computed before a rule was verified."""
    base = effective_rules_hash("abc123", {})
    verified = effective_rules_hash("abc123", {"r1": "VERIFIED"})
    rejected = effective_rules_hash("abc123", {"r1": "REJECTED"})

    assert verified != base
    assert rejected != base
    assert verified != rejected, "verifying and rejecting are different rule sets"
    # Order-independent: the same decisions must hash the same however the rows came back.
    assert effective_rules_hash("abc123", {"a": "VERIFIED", "b": "REJECTED"}) == (
        effective_rules_hash("abc123", {"b": "REJECTED", "a": "VERIFIED"})
    )


# ==========================================================================================
# the endpoints
# ==========================================================================================


def queue(client, **params) -> dict:
    response = client.get("/api/v1/rules/review-queue", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def review(client, rule_id: str, **body) -> object:
    payload = {"status": "VERIFIED", "reviewed_by": "Frau Dr. Prüfer", "review_notes": ""}
    payload.update(body)
    return client.post(f"/api/v1/rules/{rule_id}/review", json=payload)


def test_the_review_queue_lists_the_undecided_rules_with_their_evidence(client):
    body = queue(client, limit=5)

    assert body["total_constraint_rules"] == 894
    # Everything in the denominator that nobody has enforced yet is what a reviewer is offered.
    # Redundant rules are verified and enforced by their twin, so they are neither in the queue
    # nor a coverage gap — see `RuleStore._dedupe_exclusions`.
    from app.api import deps

    redundant = len(deps.pipeline().rules.redundant)
    assert body["pending_rule_count"] == (
        body["total_constraint_rules"] - body["verified_rule_count"] - redundant
    )
    assert body["pending_rule_count"] > 0, "an empty queue would make the rest of this vacuous"
    assert body["review_verified_rule_count"] == 0
    assert body["rejected_rule_count"] == 0
    assert body["truncated"] is True
    assert len(body["rules"]) == 5

    rule = body["rules"][0]
    assert rule["verified"] is False and rule["csv_verified"] is False
    assert rule["review_status"] is None
    # The evidence a reviewer actually decides from, not a summary of it.
    assert rule["quote"], "a rule with no source sentence cannot be reviewed, only rubber-stamped"
    assert rule["legal_basis"]
    assert rule["source"]
    assert rule["ziffern"]
    assert rule["kind"] in {"exclusion", "zielleistung", "specificity", "factor_cap"}


def test_the_queue_can_be_filtered_by_kind_without_hiding_the_backlog(client):
    """Filtered on exclusions rather than factor caps: every factor cap is verified now, so a
    `factor_cap` filter returns an empty page and the assertion below would hold vacuously."""
    everything = queue(client, limit=1000)
    exclusions = queue(client, kind="exclusion", limit=1000)

    assert exclusions["rules"], "no pending exclusions left — pick a kind that still has a backlog"
    assert {r["kind"] for r in exclusions["rules"]} == {"exclusion"}
    # The filter narrows the page, not the number the dashboard reports as outstanding.
    assert exclusions["pending_rule_count"] == everything["pending_rule_count"]


def test_the_queue_never_offers_a_rule_the_csv_already_verified(client):
    body = queue(client, limit=1000)

    assert all(r["csv_verified"] is False for r in body["rules"])
    assert "excl_man_5_7" not in {r["rule_id"] for r in body["rules"]}


def test_verifying_a_rule_removes_it_from_the_queue_and_moves_the_coverage(client):
    before = queue(client, limit=5)
    target = before["rules"][0]["rule_id"]

    response = review(client, target, review_notes="Anmerkung zu Nr. 4 gelesen, Extraktion korrekt.")
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["rule"]["rule_id"] == target
    assert body["rule"]["verified"] is True
    assert body["rule"]["csv_verified"] is False
    assert body["rule"]["review_status"] == "VERIFIED"
    assert body["rule"]["reviewed_by"] == "Frau Dr. Prüfer"
    assert body["rule"]["reviewed_at"]
    assert body["rule"]["review_notes"].startswith("Anmerkung")

    assert body["coverage"]["review_verified_rule_count"] == 1
    # One more rule is enforced than before, so one fewer is outstanding. Written as the identity
    # rather than a literal, because the CSV's own verified count moves as rules get curated.
    from app.api import deps

    assert body["coverage"]["unverified_rule_count"] == (
        before["total_constraint_rules"]
        - before["verified_rule_count"]
        - len(deps.pipeline().rules.redundant)
        - 1
    )

    after = queue(client, limit=1000)
    assert target not in {r["rule_id"] for r in after["rules"]}
    assert after["pending_rule_count"] == before["pending_rule_count"] - 1
    assert after["review_verified_rule_count"] == 1


def test_rejecting_a_rule_removes_it_from_the_queue_without_enforcing_it(client):
    before = queue(client, limit=5)
    target = before["rules"][0]["rule_id"]

    body = review(client, target, status="REJECTED", review_notes="Extraktion falsch.").json()

    assert body["rule"]["verified"] is False
    assert body["rule"]["review_status"] == "REJECTED"
    assert body["coverage"]["rejected_rule_count"] == 1
    assert body["coverage"]["review_verified_rule_count"] == 0

    after = queue(client, limit=1000)
    assert target not in {r["rule_id"] for r in after["rules"]}
    assert after["pending_rule_count"] == before["pending_rule_count"] - 1


def test_a_pending_review_leaves_the_rule_in_the_queue(client):
    before = queue(client, limit=5)
    target = before["rules"][0]["rule_id"]

    body = review(client, target, status="PENDING", reviewed_by="").json()
    assert body["rule"]["review_status"] == "PENDING"

    after = queue(client, limit=1000)
    parked = next(r for r in after["rules"] if r["rule_id"] == target)
    assert parked["review_status"] == "PENDING"
    assert after["pending_rule_count"] == before["pending_rule_count"], (
        "parking a rule has not made it any safer"
    )


def test_a_decision_without_a_name_is_refused(client):
    target = queue(client, limit=5)["rules"][0]["rule_id"]

    for status in ("VERIFIED", "REJECTED"):
        response = review(client, target, status=status, reviewed_by="   ")
        assert response.status_code == 422, response.text

    # PENDING is a bookmark, not a decision, so it may be unattributed.
    assert review(client, target, status="PENDING", reviewed_by="").status_code == 200


def test_a_reviewer_can_change_their_mind(client):
    """One row per rule, upserted. The table is not append-only and the docstring says why."""
    target = queue(client, limit=5)["rules"][0]["rule_id"]

    assert review(client, target, status="VERIFIED").json()["rule"]["verified"] is True
    second = review(client, target, status="REJECTED", reviewed_by="Herr Meier").json()

    assert second["rule"]["verified"] is False
    assert second["rule"]["review_status"] == "REJECTED"
    assert second["rule"]["reviewed_by"] == "Herr Meier"
    assert second["coverage"]["review_verified_rule_count"] == 0
    assert second["coverage"]["rejected_rule_count"] == 1


def test_reviewing_an_unknown_rule_is_a_404(client):
    response = review(client, "excl_auto_not_a_real_rule")

    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "rule_not_found"


def test_the_coverage_endpoint_reports_what_the_engine_is_holding(client):
    before = client.get("/api/v1/rules/coverage").json()
    assert before["total_constraint_rule_count"] == 894
    assert before["review_verified_rule_count"] == 0

    target = queue(client, limit=5)["rules"][0]["rule_id"]
    review(client, target)

    after = client.get("/api/v1/rules/coverage").json()
    assert after["review_verified_rule_count"] == 1
    assert after["enforced_rule_count"] == before["enforced_rule_count"] + 1
    assert after["unverified_rule_count"] == before["unverified_rule_count"] - 1


def test_a_review_reaches_the_running_engine_not_just_the_database(client):
    """The claim that makes the whole feature worth building.

    A verified rule has to be enforced by the next solve, not merely recorded. `/catalog` reports
    the live rule store, so the enforced count there moving is proof the merge reached the engine
    rather than stopping at the table.
    """
    before = client.get("/api/v1/catalog").json()["rule_coverage_detail"]["enforced_rule_count"]

    target = queue(client, limit=5)["rules"][0]["rule_id"]
    review(client, target)

    after = client.get("/api/v1/catalog").json()["rule_coverage_detail"]["enforced_rule_count"]
    assert after == before + 1


def synthetic_invoice(client, *ziffern: str) -> bytes:
    """A minimal PADnext payload charging exactly these Ziffern, priced from the live catalog.

    Priced rather than guessed so the audit finds no arithmetic fault and the only thing that can
    move a bucket is a rule — which is what the test is about.
    """
    from app.api import deps
    from app.validation.validator import cent_to_eur, line_amount_cent

    catalog = deps.pipeline().catalog

    def amount(ziffer: str) -> str:
        cents = line_amount_cent(
            catalog.ziffern[ziffer].punkte, Decimal("2.3"), catalog.punktwert_cent
        )
        return str(cent_to_eur(cents))

    positions = "".join(
        f'''<goziffer positionsnr="{index}" go="GOÄ" ziffer="{ziffer}">
             <datum>2026-07-20</datum><anzahl>1</anzahl><text>synthetisch</text>
             <faktor>2.3</faktor><gesamtbetrag>{amount(ziffer)}</gesamtbetrag>
           </goziffer>'''
        for index, ziffer in enumerate(ziffern, start=1)
    )
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<!-- SYNTHETIC. No real patient, no real practice, no real invoice. -->
<rechnungen anzahl="1" xmlns="http://padinfo.de/ns/pad">
  <nachrichtentyp version="02.12">ADL</nachrichtentyp>
  <rechnung id="SYNTH-RULE-REVIEW">
    <abrechnungsfall>
      <behandlungsart>0</behandlungsart><vertragsart>1</vertragsart>
      <positionen posanzahl="{len(ziffern)}">{positions}</positionen>
    </abrechnungsfall>
  </rechnung>
</rechnungen>'''.encode()


def test_verifying_a_rule_moves_euros_out_of_unconfirmed_in_a_real_audit(client):
    """End to end, and the reason any of this is worth building.

    An invoice charging the two Ziffern of a still-unverified exclusion sits entirely in
    `unconfirmed`: the engine has no verified rule bearing on either line and refuses to say
    anything about the money. Verifying that one rule has to change it in one step.

    The rule is taken from the review queue rather than named. It used to name `excl_auto_30_4`,
    which stopped working the day a verification pass verified that rule — a failure that says
    nothing about the behaviour under test. The bundled nine-position example is deliberately not
    used either: the assertion on the "before" state below is what keeps this test meaningful, and
    it only holds for an invoice no verified rule reaches.
    """
    from app.api import deps

    pending = deps.pipeline().rules.suppressed
    target = next(
        (
            r
            for r in pending
            if not r.verified and getattr(r, "from_ziffer", "") and r.from_ziffer != r.to_ziffer
        ),
        None,
    )
    if target is None:
        pytest.skip("every machine-extracted rule is verified; nothing left to promote")
    payload = synthetic_invoice(client, target.from_ziffer, target.to_ziffer)

    def audit() -> dict:
        response = client.post(
            "/api/v1/padnext/audit",
            content=payload,
            headers={"Content-Type": "application/xml"},
        )
        assert response.status_code == 200, response.text
        return response.json()

    before = audit()
    assert Decimal(before["unconfirmed_eur"]) == Decimal(before["claimed_total_eur"]), (
        "with no verified rule bearing on it, the whole invoice must be unjudgeable"
    )
    assert before["coverage_ratio"] == 0.0

    assert review(client, target.rule_id).status_code == 200

    after = audit()

    assert Decimal(after["unconfirmed_eur"]) == Decimal("0.00")
    assert Decimal(after["confirmed_wrong_eur"]) > 0, "GOÄ 4 beside GOÄ 30 is now demonstrably wrong"
    assert Decimal(after["confirmed_fine_eur"]) > 0, "and GOÄ 30 is now demonstrably fine"
    assert after["coverage_ratio"] == 1.0

    # The identity still holds, which is what makes this a re-allocation and not a leak.
    assert (
        Decimal(after["confirmed_fine_eur"])
        + Decimal(after["confirmed_wrong_eur"])
        + Decimal(after["unconfirmed_eur"])
        == Decimal(after["claimed_total_eur"])
    )
    assert Decimal(after["claimed_total_eur"]) == Decimal(before["claimed_total_eur"])

    # Both positions now name the rule that decided them, so the verdict is traceable to the review.
    assert all(target.rule_id in p["verified_rule_ids"] for p in after["positions"])

    # And the receipt moved with the rules: two audits of one invoice under different rule sets
    # must not be confusable for each other.
    assert after["receipt_hash"] != before["receipt_hash"]
