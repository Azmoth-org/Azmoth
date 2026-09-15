# F1 — 35 exclusions pointed the wrong way

Internal engineering reference. Stand: 2026-09-15. Found while cross-checking the coverage-sprint
batch 3 rows (PR #86) and fixed here, on its own, because flipping an enforced exclusion changes
which position a real invoice loses.

---

## 1. What was wrong

`apps/engine/scripts/deterministic_rule_parser.py` states the hazard in its own docstring:

> **The five sentence forms** (`d` = the Ziffer that may not be charged, `n` = the one whose
> presence forbids it; the stored edge is always `n -> d`):
>
> ```
> A  ist_neben    Die Leistung nach Nummer <d> ist neben den Leistungen nach den Nummern <n...>
>                 nicht berechnungsfähig.
> B  neben_sind   Neben der Leistung nach Nummer <n> ist die Leistung nach Nummer <d> nicht
>                 berechnungsfähig.
> ```
>
> A and D put the forbidden Ziffer first; B and E put it last. **Getting that backwards is
> precisely the mistake the extractor can make and a reader can miss.**

The extractor does not make it: all 735 one-way rows in `data/rules/exclusions.csv` point the way
their sentence does. The 35 rows below, hand-entered by coverage-sprint batch 1, are form-A
sentences recorded as if they were form B — the *subject* of the sentence, which is the position
that may not be charged, was stored as the position that survives.

Nothing could see it. The rows are well-formed, their citations are verbatim, both Ziffern exist,
the rules fire, each blocks exactly one position and prints a real paragraph of the GOÄ beside it.
Every check in this repository is satisfied by a rule pointing either way, because until now
nothing compared a stored edge against its own sentence.

---

## 2. The exact 35 rules

`from -> to` is the stored edge, and `exclusion(RuleId, A, B, 0)` in
`logic/datalog/goae_rules.dl` reads "if A is charged, B is not chargeable" — so `from` is the
position that **survives**.

| Sentence (verbatim, form A) | Was | Now |
|---|---|---|
| "Der Zuschlag nach Buchstabe A ist neben den Zuschlägen nach den Buchstaben B, C und/oder D nicht berechnungsfähig." | `excl_man_A_B` A→B<br>`excl_man_A_C` A→C<br>`excl_man_A_D` A→D | `excl_man_B_A` B→A<br>`excl_man_C_A` C→A<br>`excl_man_D_A` D→A |
| "Der Zuschlag nach Buchstabe E ist neben Zuschlägen nach den Buchstaben F, G und/oder H nicht berechnungsfähig." | `excl_man_E_F` E→F<br>`excl_man_E_G` E→G<br>`excl_man_E_H` E→H | `excl_man_F_E` F→E<br>`excl_man_G_E` G→E<br>`excl_man_H_E` H→E |
| "Der Zuschlag nach Buchstabe F ist neben den Leistungen nach den Nummern 45, 46, 48 und 52 nicht berechnungsfähig." | `excl_man_F_45` `excl_man_F_46`<br>`excl_man_F_48` `excl_man_F_52` | `excl_man_45_F` `excl_man_46_F`<br>`excl_man_48_F` `excl_man_52_F` |
| "Der Zuschlag nach Buchstabe G ist neben den Leistungen nach den Nummern 45, 46, 48 und 52 nicht berechnungsfähig." | `excl_man_G_45` `excl_man_G_46`<br>`excl_man_G_48` `excl_man_G_52` | `excl_man_45_G` `excl_man_46_G`<br>`excl_man_48_G` `excl_man_52_G` |
| "Der Zuschlag nach Buchstabe H ist neben den Leistungen nach den Nummern 45, 46, 48 und 52 nicht berechnungsfähig." | `excl_man_H_45` `excl_man_H_46`<br>`excl_man_H_48` `excl_man_H_52` | `excl_man_45_H` `excl_man_46_H`<br>`excl_man_48_H` `excl_man_52_H` |
| "Die Leistung nach Nummer 48 ist neben den Leistungen nach den Nummern 1, 50, 51 und/oder 52 nicht berechnungsfähig." | `excl_man_48_1` `excl_man_48_50`<br>`excl_man_48_51` `excl_man_48_52` | `excl_man_1_48` `excl_man_50_48`<br>`excl_man_51_48` `excl_man_52_48` |
| "Die Leistung nach Nummer 260 ist neben Leistungen nach den Nummern 355 bis 361, 626 bis 632 und/oder 648 nicht berechnungsfähig." | `excl_man_260_355` `excl_man_260_356`<br>`excl_man_260_357` `excl_man_260_360`<br>`excl_man_260_361` `excl_man_260_626`<br>`excl_man_260_627` `excl_man_260_628`<br>`excl_man_260_629` `excl_man_260_630`<br>`excl_man_260_631` `excl_man_260_632`<br>`excl_man_260_648` | `excl_man_355_260` `excl_man_356_260`<br>`excl_man_357_260` `excl_man_360_260`<br>`excl_man_361_260` `excl_man_626_260`<br>`excl_man_627_260` `excl_man_628_260`<br>`excl_man_629_260` `excl_man_630_260`<br>`excl_man_631_260` `excl_man_632_260`<br>`excl_man_648_260` |

**35 rows, 7 sentences.** Ids move with the columns because every one of the 948 exclusion rows in
this repo encodes its own edge in its id — `test_every_rule_id_still_encodes_its_own_edge` now
enforces that, since the id is the only place the direction is visible without opening the CSV and
reading German, and an id that disagrees with its columns is how a corrected rule gets "corrected"
back.

**Sentences deliberately *not* touched**, because they are form B and were already right:
`excl_man_C_B`, `excl_man_G_F` ("Neben dem Zuschlag nach Buchstabe C ist der Zuschlag nach
Buchstabe B nicht berechnungsfähig"), the nineteen GOÄ 45/46 Visite rows, `excl_man_1473_1485`,
and the seven `excl_man_5378_*`. They are in the new test's `DIRECTED_PAIRS` so that "fixing" them
fails too.

---

## 3. Two harms, both reproduced against the real engine

### 3.1 The wrong position is suppressed — 31 rows

| Charged together | Was suppressed (wrong) | Now suppressed (correct) | Δ on the invoice |
|---|---|---|---|
| A + B | GOÄ B (10,49 €) | GOÄ A (4,08 €) | −6,41 € |
| A + C | GOÄ C (18,65 €) | GOÄ A (4,08 €) | −14,57 € |
| A + D | GOÄ D (12,82 €) | GOÄ A (4,08 €) | −8,74 € |
| E + F | GOÄ F (15,15 €) | GOÄ E (9,33 €) | −5,82 € |
| E + G | GOÄ G (26,23 €) | GOÄ E (9,33 €) | −16,90 € |
| E + H | GOÄ H (19,82 €) | GOÄ E (9,33 €) | −10,49 € |
| F + 45 | GOÄ 45 (9,38 €) | GOÄ F (15,15 €) | +5,77 € |
| F + 46 | GOÄ 46 (6,70 €) | GOÄ F (15,15 €) | +8,45 € |
| F + 48 | GOÄ 48 (16,09 €) | GOÄ F (15,15 €) | −0,94 € |
| F + 52 | GOÄ 52 (13,41 €) | GOÄ F (15,15 €) | +1,74 € |
| G + 45 … G + 52 | GOÄ 45/46/48/52 | GOÄ G (26,23 €) | +10,14 … +19,53 € |
| H + 45 … H + 52 | GOÄ 45/46/48/52 | GOÄ H (19,82 €) | +3,73 … +13,12 € |
| 260 + 355 | GOÄ 355 (80,44 €) | GOÄ 260 (26,81 €) | −53,63 € |
| 260 + 626 | GOÄ 626 (134,06 €) | GOÄ 260 (26,81 €) | −107,25 € |
| 260 + 648 | GOÄ 648 (81,11 €) | GOÄ 260 (26,81 €) | −54,30 € |

Fees at the Regelhöchstsatz 2,3× (1,0× for the Zuschläge, which their own Allgemeine Bestimmung
caps there). **Δ is what the audit's `confirmed_wrong_eur` moves by** — negative means the engine
was flagging *more* money than it should have, positive that it was flagging less. The GOÄ 260
rows are the largest: an arterial or central venous catheter beside an angiography was losing the
angiography, a hundred euro position, instead of the twenty-six euro catheter.

### 3.2 A correct rule was silenced — 4 rows, and this is the worse half

`excl_man_48_1`, `_48_50`, `_48_51`, `_48_52` each had a **correct** auto-extracted twin
(`excl_auto_1_48`, `excl_auto_50_48`, …) already in `exclusions.csv`. LAYER 3 of
`logic/datalog/goae_rules.dl` decides a one-way edge only when the opposite edge is absent:

```
blocked_exclusion(B, A, RuleId) :-
    …
    exclusion(RuleId, A, B, 0),
    !exclusion(_, B, A, _),
```

With both present, **neither fires.** Before this fix:

```
GOÄ 48 + GOÄ 50  ->  billable ['48', '50'], blocked []
GOÄ 48 + GOÄ  1  ->  billable ['1', '48'],  blocked []
```

Two verified rules, one of them correct, enforcing nothing — and no coverage figure in this
repository could show it, because both Ziffern are "under rule" and both rules are "enforced".
After the fix each of those four combinations is caught, and GOÄ 48 (16,09 €) is the position that
goes, which is what its Anmerkung says.

---

## 4. Impact on the golden suite: none

`apps/engine/scripts/refreeze_rule_coverage.py` reports **METADATA ONLY for all nine** frozen
snapshots. No Ziffer, factor, amount or proof moved on any of them; the 48 updated leaves are rule
counts and the warning sentence that quotes them. No golden case contains an affected pair.

A sweep over every committed fixture corpus — `apps/engine/tests/golden/`, `logic/tests/cases/`,
`logic/tests/golden/`, `padnext_example/`, `apps/engine/tests/fixtures/` — finds **no file
containing both members of any of the 35 pairs**.

Case A's `receipt_hash` moved, because `rules_hash()` covers every byte of `data/rules/*.csv` and
35 rows changed. Re-pinned after confirming stability across two separate processes, exactly as
batches 1 and 2 did. `logic_version` (`83fae8e7f0369c25`) is unchanged: nothing under `logic/` was
touched.

---

## 5. Impact on deployed invoices

**No stored result changes.** `proposals` rows are write-once snapshots of one solve, carrying the
`receipt_hash` of the engine state that produced them (`app/db/models.py`). Nothing re-evaluates
them, and this change does not either.

**No stale result can be served.** `app/services/cache.py` keys every cached result on
`rules_hash`, which moved — so every cached entry for every organisation is now a miss, by
construction. The module says why that matters: *"A cache that could serve a result computed under
a different rule set would be a compliance defect, not a performance one."*

**A re-submitted delivery gets a different answer if and only if it contains one of the 35 pairs**
— §3's tables say which position moves and by how much. The two answers are distinguishable
because `receipt_hash` differs, and `proposals.receipt_hash` is indexed precisely for this: *"show
me every proposal produced by this exact engine state is the query a Rechnungsprüfer asks, and the
one that makes a recall tractable."*

**Scoping a recall.** Any proposal whose positions contain one of the 35 pairs was decided by a
rule that pointed the wrong way (or, for the four GOÄ 48 pairs, by no rule at all). Whether those
proposals need re-running is a business call, not an engineering one — it depends on whether they
were exported. What matters technically is that the set is identifiable: the pairs are enumerated
above, and both the old and new engine states have distinct receipt hashes.

There is one asymmetry worth stating plainly: for the pairs where Δ is **negative**, the engine
had been telling a practice that a position was not chargeable when it was. Those are invoices
where a practice may have dropped a line it was entitled to bill. That is the direction of error
that costs a customer money rather than a payer, and the GOÄ 260 rows are the expensive ones.

---

## 6. The regression test

`apps/engine/tests/test_exclusion_direction.py` — 30 tests. It checks **every exclusion the engine
loads** (948 rows across `exclusions.csv` and `exclusions.manual.csv`), not the 35, because the 35
were only a symptom: the defect was that nothing compared a stored edge against its own sentence.

* `test_no_exclusion_runs_opposite_to_the_sentence_it_quotes` — re-derives each row's edge from
  its own `quote` using `deterministic_rule_parser`, which shares no code with whatever produced
  the row and decides direction structurally, from where `neben` sits relative to the verb.
* `test_every_unreadable_sentence_has_a_written_reading` — the guard on the guard. 47 rows quote a
  sentence the parser returns `None` for (a blocker named by its Leistungslegende rather than its
  number, both sides named by Buchstabe, `ist die Nummer` where `_B_SPLIT` expects `ist die
  Leistung`). Each is enumerated with the reading that justifies it, so a future sentence shape the
  parser chokes on cannot pass silently. All eleven such sentences are form B or E.
* `test_the_cross_check_actually_covers_the_corpus` — ≥ 90 % machine-confirmed, so the file cannot
  decay into a list of hand-waves.
* `test_every_rule_id_still_encodes_its_own_edge` — all 948.
* `test_the_engine_suppresses_the_side_the_sentence_forbids` — 21 pairs claimed on a real invoice
  through the `souffle` fixture, asserting *which* Ziffer disappears and *which rule id* says so.
  A CSV can be right while the Datalog layer does nothing with it.
* `test_the_pairs_a_reversed_rule_had_silenced_are_caught_again` — §3.2, specifically.

**Verified to fail on the defect**: with the CSV fix stashed and the test kept,
`22 failed, 8 passed`. With the fix applied, `30 passed`.

`apps/engine/tests/test_f1_migration.py` — 6 tests over the rename list: that it is 35 unique
pairs, that every target id exists as a rule and no source id still does, that no id is both a
source and a target (which is why the migration can update row by row without ordering), that each
rename is the same edge reversed, and that the migration's own statement actually moves a review
and its downgrade puts it back.

---

## 7. Why a database migration

`rule_reviews.rule_id` has no foreign key, by design — `app/db/models.py`: *"the thing it points
at is not in this database"*. So nothing stops a renamed id from orphaning a review, and an
orphaned review is not inert: `RuleStore.with_reviews` resolves by id, a review it cannot find is
silently not applied, and a rule a human had **REJECTED** would start enforcing again.

In practice the table is expected to hold none of these ids — `GET /rules/review-queue` only
offers rules that are unverified in the CSV, and all 35 are `verified: true`. But
`POST /rules/{rule_id}/review` accepts any id the store knows, so "expected" is not "guaranteed",
and a rename that is correct almost always and silently un-rejects a rule the rest of the time is
not a rename worth shipping.

`alembic/versions/20260915_0014_f1_exclusion_direction_rule_ids.py` maps the 35 ids, and
downgrades.

---

## 8. Numbers

| | Before | After |
|---|---|---|
| Ziffern named by ≥ 1 enforced rule | 383 / 2,343 | **383 / 2,343** (unchanged) |
| `total_constraint_rule_count` | 980 | **980** (unchanged) |
| `enforced_rule_count` | 944 | **940** |
| `RuleStore.redundant` | 30 | **34** |

No rule was added or removed: 35 rows changed direction and nothing else. Coverage is unchanged
because it counts Ziffern named by a rule, and the same Ziffern are named — the other way round.

`enforced_rule_count` falls by four for a reason that is the fix working. Once
`excl_man_48_1` and its three siblings point the right way they assert the edge their
auto-extracted twin already asserts, so `_dedupe_exclusions` keeps the hand-curated rule (whose
citation a human wrote) and moves the auto twin to `redundant` — counted as loaded, not enforced.
Four fewer enforced rules, and four more combinations the engine actually catches.

```
# regenerate every figure above
cd apps/engine
python scripts/engine_cli.py check
python scripts/refreeze_rule_coverage.py          # dry run; --write to apply
python -m pytest tests/test_exclusion_direction.py tests/test_f1_migration.py
```
