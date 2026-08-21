% =============================================================================================
% GOÄ OPTIMISATION — Clingo Answer Set Program
% =============================================================================================
% Decides only what the Datalog layer deliberately left open:
%
%   1. Which member of a mutually exclusive cluster is charged (arbitration).
%   2. Which Steigerungsfaktor each charged position carries (§ 5, § 12 Abs. 3 GOÄ).
%   3. Which listed position an unlisted service is charged analogously to (§ 6 Abs. 2 GOÄ).
%
% The solver may only ever choose among positions that were proposed and are in the catalog. It
% cannot invent a Ziffer: `bill/1` is derivable only from `fixed/1` or `arbitrate/1`, both of
% which are injected facts.
%
% OBJECTIVE ORDERING — lexicographic, and revenue is LAST
%
%   @5  never charge an analog position that is already charged directly
%   @4  never leave a documented, chargeable service off the invoice entirely
%   @3  prefer the position with the stronger clinical evidence
%   @2  prefer the more specific position
%   @1  higher total points  <- tiebreaker only
%
% Evidence and specificity outrank money on purpose. An objective that maximised revenue would
% systematically pick whichever of two competing positions pays more, which is upcoding. Here
% money only separates options that are equally well evidenced and equally specific, and no
% objective can touch a hard constraint — those are integrity constraints.
%
% EVERY NON-INTEGER IS SCALED BY 100. ASP has no floats: factor 2.3 is 230, confidence 0.95 is 95.
% =============================================================================================

% --- INPUT (injected by app/optimization/clingo_solver.py) ---
% code_info(Z, Punkte, Category).      catalog facts for every position in play
% conf(Z, Confidence100).              strongest evidence behind a proposed position
% spec_priority(Z, Priority).          mapping specificity/priority
% fixed(Z).                            Datalog proved this chargeable — not re-opened here
% arbitrate(Z).                        survived every hard rule, but has a mutual competitor
% excluded(A, B).                      A charged => B not chargeable
% zielleistung(P, C).                  C is a component of target service P
% conflict_pair(A, B).                 mutually exclusive, needs a decision
% sf(Z, Threshold100, Max100).         resolved § 5 band per position
% cap(Z, Max100).                      per-position cap from a Leistungslegende
% justification(Z, SeverityRank).      1 = leicht, 2 = mittel, 3 = schwer
% encounter_justification(SeverityRank).
% base_policy(schwellenwert | einfachsatz).
% analog_needed(Act, EntityType).
% analog_cand(Act, Z, Similarity100).

#defined code_info/3.
#defined conf/2.
#defined spec_priority/2.
#defined fixed/1.
#defined arbitrate/1.
#defined excluded/2.
#defined zielleistung/2.
#defined conflict_pair/2.
#defined sf/3.
#defined cap/2.
#defined justification/2.
#defined encounter_justification/1.
#defined base_policy/1.
#defined analog_needed/2.
#defined analog_cand/3.

% =============================================================================================
% CHOICES
% =============================================================================================

% Conclusions the rules engine already proved are not renegotiated.
bill(Z) :- fixed(Z).
{ bill(Z) } :- arbitrate(Z).

% Exactly one analog position per unlisted service (§ 6 Abs. 2 GOÄ).
has_analog_cand(A, Z) :- analog_cand(A, Z, _).
1 { analog(A, Z) : has_analog_cand(A, Z) } 1 :- analog_needed(A, _).

charged(Z) :- bill(Z).
charged(Z) :- analog(_, Z).

% =============================================================================================
% HARD CONSTRAINTS — legality. No objective can trade these away.
% =============================================================================================

:- bill(A), bill(B), excluded(A, B), A != B.
:- bill(C), bill(P), zielleistung(P, C).

% A charged position must exist in the catalog. Belt and braces: `bill/1` cannot be derived for
% anything that was not injected, but an inconsistent injection would be caught here.
:- charged(Z), not code_info(Z, _, _).

% =============================================================================================
% STEIGERUNGSFAKTOR (§ 5 Abs. 2 GOÄ, § 12 Abs. 3 GOÄ)
% =============================================================================================
% Ladder: no documented reason -> the Schwellenwert (which needs no written justification);
% a documented reason escalates within the legal band; the Höchstsatz caps it; and a
% Leistungslegende cap ("nur mit dem einfachen Gebührensatz") overrides everything.

sev(Z, S) :- charged(Z), justification(Z, S).
sev(Z, S) :- charged(Z), encounter_justification(S).
has_sev(Z) :- sev(Z, _).
maxsev(Z, S) :- has_sev(Z), S = #max { T : sev(Z, T) }.

ladder(Z, T)   :- charged(Z), not has_sev(Z), base_policy(schwellenwert), sf(Z, T, _).
ladder(Z, 100) :- charged(Z), not has_sev(Z), base_policy(einfachsatz).
ladder(Z, T)   :- charged(Z), maxsev(Z, 1), sf(Z, T, _).
ladder(Z, F)   :- charged(Z), maxsev(Z, 2), sf(Z, T, M), F = T + 30, F <= M.
ladder(Z, M)   :- charged(Z), maxsev(Z, 2), sf(Z, T, M), T + 30 > M.
ladder(Z, M)   :- charged(Z), maxsev(Z, 3), sf(Z, _, M).

has_cap(Z) :- cap(Z, _).
factor(Z, F) :- ladder(Z, F), not has_cap(Z).
factor(Z, C) :- ladder(Z, F), cap(Z, C), C < F.
factor(Z, F) :- ladder(Z, F), cap(Z, C), F <= C.

% Invariant: exactly one factor per charged position. Reported to the caller rather than
% enforced as a constraint, so a modelling gap surfaces as a clear error instead of an empty
% answer set that looks like "nothing is chargeable".
factor_count_bad(Z) :- charged(Z), #count { F : factor(Z, F) } != 1.

% A factor above the Schwellenwert is lawful only with a written reason (§ 12 Abs. 3 GOÄ).
justification_required(Z) :- factor(Z, F), sf(Z, T, _), F > T.

% =============================================================================================
% OBJECTIVES
% =============================================================================================

% @5 — do not charge an analog position that is already charged directly. Kept soft so an
% over-constrained candidate set degrades into a reported warning, not an UNSAT program.
analog_collision(A, Z) :- analog(A, Z), bill(Z).
#minimize { 1@5, A, Z : analog_collision(A, Z) }.

% @4 — a documented service must not vanish from the invoice entirely.
covered(A, B) :- conflict_pair(A, B), bill(A).
covered(A, B) :- conflict_pair(A, B), bill(B).
#maximize { 1@4, A, B : covered(A, B) }.

% @3 — stronger clinical evidence wins. This is what decides Nr. 5 vs Nr. 7.
#maximize { C@3, Z : bill(Z), conf(Z, C) }.

% @2 — the more specific position wins.
#maximize { P@2, Z : bill(Z), spec_priority(Z, P) }.
#maximize { S@2, A, Z : analog(A, Z), analog_cand(A, Z, S) }.

% @1 — revenue, as the final tiebreaker only.
#maximize { P@1, Z : charged(Z), code_info(Z, P, _) }.

% =============================================================================================
% OUTPUT
% =============================================================================================
#show bill/1.
#show analog/2.
#show factor/2.
#show justification_required/1.
#show analog_collision/2.
#show factor_count_bad/1.
#show maxsev/2.
