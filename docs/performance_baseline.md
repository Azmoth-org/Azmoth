# Performance baseline — where the time actually goes

**Measured 2026-08-23** on the three committed golden cases. Every number here was produced by
`engine_cli.py solve --stats`, seven cold processes per case, median reported. Nothing in this
document changes what the engine bills: task 1.3 was measurement only, and the ASP encoding, the
Datalog program and the objective ordering are untouched.

Read the headline first, because it is not the one the task assumed:

> **Clingo is not the bottleneck.** Pure Clingo search is **0.42–0.47 ms**, under **0.6 %** of a
> request. Two Soufflé subprocess invocations are **72 %**. The ground programs are 92–143 atoms —
> three orders of magnitude below anything Clingo finds difficult.

That does not make the profiling wasted: the scaling experiments in §4 show exactly *which* inputs
would make Clingo expensive, and the answer is specific enough to act on.

---

## 1. Environment

| | |
|---|---|
| CPU | Intel Core i5-10300H @ 2.50 GHz, 8 threads |
| Python | 3.11.15 |
| clingo | 5.8.0 (Python API, `--models=0 --opt-mode=opt`, single-threaded) |
| Soufflé | 2.5, **interpreted** (no `-c`), one subprocess per evaluation |
| catalog | `goae_official_snapshot_2026-07-25`, 2192 Ziffern |
| rules | 30 enforced exclusions, 862 advisory / unverified |
| `SOLVER_TIMEOUT_SECONDS` | 5.0 (production default) |

Laptop numbers, on a machine with a browser open. Treat the **ratios** as the finding and the
absolute milliseconds as an order of magnitude.

## 2. The three golden cases

Median of 7 cold runs, in milliseconds. A cold run pays catalog and rule loading; a served request
does not, because both loaders are `lru_cache`d and a long-running process pays them once at boot.

| stage | case_001 knee | case_002 cardiology | case_003 dermatology |
|---|---:|---:|---:|
| catalog + rules load *(once per process)* | 26.05 | 25.90 | 25.62 |
| input parse + schema validation | 0.19 | 0.20 | 0.16 |
| bridge (entity → Ziffer) | 0.80 | 0.90 | 0.79 |
| **Soufflé — rules pass** | **27.67** | **28.12** | **27.35** |
| Clingo — build facts | 0.17 | 0.21 | 0.16 |
| Clingo — ground | 1.66 | 1.79 | 1.63 |
| **Clingo — solve** | **0.42** | **0.43** | **0.47** |
| **Soufflé — verification pass** | **27.54** | **28.05** | **27.32** |
| validation + pricing | 7.34 | 7.52 | 7.51 |
| receipt + cache + coverage | 9.49 | 10.57 | 9.11 |
| `solve_time_ms` (payload) | **0.42** | **0.43** | **0.47** |
| `total_time_ms` (payload, symbolic pipeline) | 67.06 | 68.87 | 66.52 |
| **end-to-end per case incl. parse** | **76.77** | **79.50** | **75.78** |

Share of a case, averaged over the three: Soufflé **72 %**, validation + pricing 10 %,
receipt/cache/coverage 12 %, Clingo grounding 2.2 %, **Clingo search 0.6 %**.

### What each case actually asks the solver

| | case_001 knee | case_002 cardiology | case_003 dermatology |
|---|---:|---:|---:|
| distinct candidate Ziffern | 8 | 10 | 5 |
| proved billable by Soufflé (`fixed`) | 4 | 8 | 5 |
| left open for arbitration | 2 | 2 | 0 |
| mutual-conflict pairs | 1 | 1 | 0 |
| analog requests (§ 6 Abs. 2) | 0 | 0 | 1 |
| invoice lines produced | 5 | 9 | 6 |

### The ground program Clingo searched

| | case_001 | case_002 | case_003 |
|---|---:|---:|---:|
| atoms (0 auxiliary in all three) | 92 | 143 | 94 |
| rules | 98 | 149 | 96 |
| — of which choice / minimize | 2 / 4 | 2 / 4 | 1 / 4 |
| bodies | 10 | 10 | 10 |
| injected fact lines | 36 | 55 | 32 |
| program text handed to clingo | 8253 B | 8694 B | 8229 B |
| search: choices / conflicts | 3 / 2 | 3 / 2 | 4 / 0 |
| models enumerated to optimum | 2 | 2 | 3 |

Clingo's native statistics API wired up cleanly and is used: `clingo.Control.statistics` is read
after every solve into `OptimizationResult.grounding`, without needing the `--stats` command-line
option (that flag only raises the *detail* level; `problem.lp` and `solving.solvers` are always
populated). The reader is wrapped in a `try/except` that degrades to `None` — grounding counts are
diagnostics, and a clingo release that renames a statistics key must never fail a solve that
already produced a correct invoice. When they are absent, `--stats` says so and the timing deltas
in the table above remain.

Note the ground program is **larger than the answer**: ~5 kB of it is the fixed encoding, and
8.2 kB of program text yields 92 atoms. At this size grounding cost is dominated by parsing the
program text, not by instantiation — which is why case_003 (32 fact lines) and case_002 (55 fact
lines) ground in the same 1.7 ms.

## 3. Where the time really goes: Soufflé, twice

55 ms of a 77 ms case is two `souffle` subprocesses. The cost is almost entirely fixed overhead,
not evaluation:

- Soufflé is invoked **interpreted** (`souffle -F facts -D out program.dl`), so every call
  re-parses and re-plans `goae_rules.dl` from source.
- Each call spawns a process, writes a fact directory, and reads TSV back.
- The evidence that it is overhead and not work: case_003 injects 32 fact lines and case_002
  injects 55, and both take the same ~28 ms. The per-fact cost is invisible.

Two remedies exist and neither is in scope here: compile the Datalog once with `souffle -c` (or
`--generate` + a shared library) and stop paying the parse per request, or keep a warm evaluator.
Either would take a request from ~77 ms to roughly ~25 ms. **This, not Clingo, is the optimisation
with a return.**

## 4. Grounding analysis — what would make Clingo expensive

The golden cases cannot show a grounding problem, so the growth curves were measured directly:
`ClingoSolver.solve()` driven with synthetic `RulesResult` objects built from real catalog Ziffern
(real `code_info`, real § 5 bands, the real encoding), varying only how many positions are in play
and how they conflict. Medians of 3, `SOLVER_TIMEOUT_SECONDS` raised to 60 so the measurement is
not clipped.

### 4a. Marginal cost, measured exactly

| what is added | ground atoms | ground rules |
|---|---:|---:|
| one more position in play | **13** | **13** |
| one more `conflict_pair(A,B)` fact | **2** | **3** |

Both are *linear in the facts injected*. There is no cross-join in the encoding — no rule in
`goae_optimize.lp` has two unbound Ziffer variables. Every quadratic below is quadratic in the
**data**, i.e. in how many `conflict_pair` facts Soufflé emits.

Counted by predicate (grounding the real encoding with 4 and then 8 positions and taking the
difference), one more position in play instantiates **9 symbolic atoms** — `code_info`, `sf`,
`conf`, `spec_priority`, `fixed`, `bill`, `charged`, `ladder`, `factor` — which clingo's
`problem.lp` reports as 13 atoms and 13 rules once minimize elements and bodies are counted. A
position that carries a documented § 12 Abs. 3 justification instantiates **14** symbolic atoms
(18 in `problem.lp`): `justification`, `sev`, `has_sev`, `maxsev` and `justification_required`
appear on top.

The 3 rules per conflict pair are exactly:

```prolog
covered(A, B) :- conflict_pair(A, B), bill(A).     % 1 ground rule per pair
covered(A, B) :- conflict_pair(A, B), bill(B).     % 1 ground rule per pair
#maximize { 1@4, A, B : covered(A, B) }.           % 1 ground minimize element per pair
```

plus the hard constraint `:- bill(A), bill(B), excluded(A,B), A != B`, one ground constraint per
injected `excluded/2` fact.

### 4b. Growth with positions in play (no conflicts — everything `fixed`)

| positions | atoms | rules | ground ms | solve ms |
|---:|---:|---:|---:|---:|
| 10 | 132 | 134 | 1.68 | 0.19 |
| 20 | 262 | 264 | 1.91 | 0.20 |
| 50 | 652 | 654 | 2.89 | 0.28 |
| 100 | 1302 | 1304 | 4.35 | 0.32 |
| 200 | 2602 | 2604 | 7.40 | 0.44 |
| 400 | 5202 | 5204 | 14.10 | 0.59 |

**A large invoice is not a slow invoice.** 400 positions with nothing to decide grounds in 14 ms
and solves in 0.6 ms. Position count alone is not the risk factor.

### 4c. Growth with open arbitration choices (n/2 disjoint conflict pairs)

Every position is an `arbitrate/1`, so each pair is one binary decision the solver must make.

| positions | pairs | atoms | ground ms | **solve ms** | search choices |
|---:|---:|---:|---:|---:|---:|
| 20 | 10 | 301 | 2.02 | 2.09 | 247 |
| 50 | 25 | 751 | 3.25 | 11.12 | 1 365 |
| 100 | 50 | 1501 | 5.26 | 56.19 | 5 328 |
| 200 | 100 | 3001 | 9.14 | 343.53 | 23 412 |
| 250 | 125 | 3751 | 10.48 | 538.56 | 38 966 |
| 300 | 150 | 4501 | 14.88 | **910.11** | 66 977 |
| 350 | 175 | 5251 | 14.16 | **1390.91** | 94 312 |
| 400 | 200 | 6001 | 17.21 | **2139.22** | 126 603 |

Grounding stays linear and cheap throughout — 17 ms at 400 positions. **Search is what grows**,
super-linearly: 4× the positions between 100 and 400 costs 38× the solve time. The driver is the
branch-and-bound over five lexicographic objective levels: each open `{ bill(Z) } :- arbitrate(Z)`
doubles the model space, and `--opt-mode=opt` must prove optimality at every level.

### 4d. Growth with conflict-pair density (all-pairs clique)

The pathological data shape: one mutual-exclusion cluster where every position conflicts with
every other, so pairs = n(n−1)/2.

| positions | pairs | atoms | rules | **ground ms** | solve ms |
|---:|---:|---:|---:|---:|---:|
| 20 | 190 | 661 | 855 | 3.22 | 0.82 |
| 50 | 1 225 | 3 151 | 4 380 | 10.09 | 3.27 |
| 100 | 4 950 | 11 301 | 16 255 | 35.66 | 15.75 |
| 200 | 19 900 | 42 601 | 62 505 | 139.39 | 106.94 |
| 400 | 79 800 | 165 201 | 245 005 | **582.94** | 1827.51 |

Here grounding *is* the problem: 245 000 ground rules from 400 positions, 583 ms to instantiate
before search begins. This is the "grounding explosion" the task asked about, and it is entirely
attributable to the three `covered/2` + `@4` rules above being instantiated once per emitted
`conflict_pair` fact.

**How real is it?** The golden cases emit 1 pair each. The GOÄ does contain genuine mutual clusters
— Nrn. 5/6/7/8 and 422–424 are documented in `goae_rules.dl` — but they are small. The clique row
matters as the shape to watch, not as today's traffic: it becomes reachable if a future rule import
turns a large family of Ziffern into one all-pairs cluster.

## 5. Soufflé migration candidates

Two candidates, ranked by measured grounding removed per unit of risk. Both are *pre-filters or
derivations*, not decisions: neither touches what the solver chooses, which is the condition for
moving work out of the ASP at all.

### Candidate 1 — collapse mutual-exclusion cliques to cluster facts *(highest value)*

**Today.** Soufflé emits `conflict(A, B, RuleId)` for every mutually exclusive pair, and
`build_facts` injects one `conflict_pair/2` per pair. A cluster of *n* positions costs n(n−1)/2
facts → 3n(n−1)/2 ground rules. At n = 400 that is 245 005 ground rules and 583 ms of grounding.

**Proposed.** Soufflé already has the ingredients (`conflict/3`, `in_conflict/1`) to compute the
connected components of the mutual-exclusion graph and emit `conflict_cluster(ClusterId, Z)` — *n*
facts instead of n(n−1)/2. The ASP's "do not leave a documented service off the invoice" objective
becomes one `#maximize` term per cluster instead of one per pair, and `1 { bill(Z) : cluster(C,Z) } 1`
expresses the exclusivity directly.

**Measured saving.** At n = 200 the ground program falls from 42 601 atoms / 62 505 rules to
roughly 3 000 — the 2 602 atoms the same 200 positions cost with no conflicts at all, plus one
cluster fact each. That is a **~93 % reduction**, and grounding from 139 ms to under 10 ms. Nothing
is saved on today's golden cases (1 pair each), which is the honest caveat: this is insurance
against a rule-import shape, not a win on current traffic.

**Risk.** Medium. Computing components is textbook Datalog and Soufflé is stratified, so it stays
explainable. But the semantics change subtly — an all-pairs clique and a connected component are
only the same thing when the exclusion relation is transitive within the cluster, and the GOÄ's is
not guaranteed to be. Needs the rule data checked before it ships, and the `conflict_pair` path
kept for non-clique clusters.

### Candidate 2 — derive the § 5 factor ladder in Soufflé, not in ASP

**Today.** The ladder chain — `charged/1`, `sev/2`, `has_sev/1`, `maxsev/2`, `ladder/2` (six
rules), `has_cap/1`, `factor/2`, `justification_required/1` — is **3 of the 9** symbolic atoms a
position instantiates when nothing is documented, and **7 of the 14** when a § 12 Abs. 3
justification is present. It is the largest single group in the per-position cost, and the golden
cases document justifications, so the 50 % figure is the realistic one.

**Why it is a filter, not a decision.** The ladder is a pure function of injected facts —
`justification/2`, `encounter_justification/1`, `sf/3`, `cap/2`, `base_policy/1`. No choice atom
appears in any of its bodies, and `factor/2` feeds **no objective**: the `@1` revenue term reads
`code_info` points, not the factor. The solver derives it, ships it back, and the Python layer
re-reads it. Soufflé already owns the neighbouring half of the same law — `factor_band/3`,
`needs_justification/3`, `invalid_factor/3` are Layer 5 of `goae_rules.dl`, and the verification
pass already re-derives factor legality there for the chosen positions.

**Measured saving.** Between **33 %** (nothing documented) and **50 %** (a justification per
position) of the per-position grounding cost. The 400-position no-conflict program would fall from
5 202 atoms to roughly 3 500, and its 14 ms grounding to under 10 ms. It does nothing at all for
the clique case, where conflict pairs dominate — which is why it ranks second.

**Risk.** Low–medium mechanically, but this is § 5 GOÄ: the ladder decides money, so moving it is a
change that needs the same legal review as changing it. The one real subtlety is `charged/1` — the
ladder currently applies to whatever the solver chose, so a Soufflé derivation would either compute
factors for every candidate (wasteful but safe) or move to a post-solve pass (cheaper, and the
natural fit given the verification pass already runs after the solve).

### Explicitly *not* a candidate

`:- bill(A), bill(B), excluded(A,B), A != B` and `:- bill(C), bill(P), zielleistung(P,C)` look like
pure filters, and Soufflé does resolve one-way exclusions and Zielleistung already (Layers 2–3 of
`goae_rules.dl`). They stay: for two *arbitration candidates* the constraint is genuinely load
bearing — Soufflé deliberately declines to pick a winner and hands the pair over. For pairs where
one side is `fixed`, `ClingoSolver._precheck` already refuses the input in Python before grounding.
One ground constraint per injected `excluded/2` fact is a small price for a legality guarantee
enforced where the choice is made.

## 6. What counts as a slow case

> **A solve is slow when `solve_time_ms` exceeds 1000 ms.** Today's golden cases are at
> 0.42–0.47 ms — **more than 2 000× under** the threshold.

Three graded thresholds, each with the observed trigger:

| level | threshold | measured trigger |
|---|---|---|
| normal | `solve_time_ms` < 50 ms | anything up to ~100 positions with ≤ 50 open pairs |
| watch | 50–1000 ms | 100–300 positions with n/2 open arbitration pairs, or a ~200-member conflict clique |
| **slow** | **> 1000 ms** | **≳ 310 positions with ~155 open arbitration pairs** (measured: 300 pairs→910 ms, 350→1391 ms) |
| at risk of timeout | > 5000 ms = `SOLVER_TIMEOUT_SECONDS` | not reached by any shape tested up to 400 positions |

**The hypothesis, stated so it can be falsified.** Slowness tracks the number of *open arbitration
choices*, not the number of positions:

- 400 positions with **zero** open choices: 0.59 ms. Not slow.
- 300 positions with **150** open choices: 910 ms. Nearly slow.
- 400 positions with **200** open choices: 2139 ms. Slow.

So the predictor is `len(rules_result.conflicts)`, available *before* Clingo is called. Roughly:
solve time is negligible below ~50 conflict pairs, and crosses one second at about **150 mutual
conflict pairs**. A separate, rarer path to slowness is grounding: a single mutual-exclusion cluster
above ~300 members spends over half a second instantiating `covered/2` before search starts —
candidate 1 above is the fix for exactly that.

**What none of this is.** No golden case is anywhere near any threshold, and no case tested reached
the 5 s timeout. The thresholds are for the monitoring that comes next: alert on
`solve_time_ms > 1000`, and log `len(conflicts)` with it, because that is the number that will
explain the alert.

## 7. Reproducing this

```bash
cd apps/engine
.venv/bin/python scripts/engine_cli.py solve ../../logic/tests/cases/case_001_knee/input.json --stats
```

`--stats` prints startup, per-case stage timings with their shares, the two payload metrics and the
ground-program statistics. It composes with `--json`, which emits the full proposal first and the
breakdown after.

The two payload metrics are in every response and need no flag:

- `solve_time_ms` — pure Clingo search, grounding and fact generation excluded.
- `total_time_ms` — end to end for the request.

They describe the **run**, not the request. `Proposal.solve_time_ms` and
`Proposal.total_time_ms` are flattened up from `audit_trail`, the way `solver_status` already is,
and `_to_proposal` derives them from the stored audit trail rather than from their own columns —
so a proposal read back from the database next year still reports what its own run cost.

The consequence to know before building a dashboard on them: a **cache hit repeats the timings of
the run that filled the cache**, because that is the work the result came from. Read `cached`
first, or you will be measuring your hit rate rather than your engine. `total_time_ms` covers the
symbolic pipeline (bridge → Soufflé → Clingo → verification → validation); the receipt, the cache
write and the coverage build sit outside it, and `--stats` reports them on their own line.

Neither number includes catalog or rule loading, because a served request does not pay it: both
loaders are `lru_cache`d, so a long-running process pays the ~26 ms once at boot. That is why
`--stats` prints startup in its own section.

Both fields are in `VOLATILE_KEYS`, so they cannot move a receipt hash or a cache key, and the
golden snapshots do not see them — `tests/test_performance_metrics.py` asserts exactly that, in
both directions.

`PadnextAuditReport` carries the same two field names, but `solve_time_ms` there measures the
**Soufflé** evaluation: the audit path never runs Clingo, because the invoice already exists and
the question is only whether its positions hold.
