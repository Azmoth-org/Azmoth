/**
 * The synthetic cases the review screen can run.
 *
 * The three `.json` files are byte-identical copies of `logic/tests/cases/<case>/input.json` — the
 * same fixtures the engine's own golden tests run against. They are duplicated here rather than
 * imported across the workspace boundary so that `apps/web` builds without the engine present.
 *
 * SYNTHETIC ONLY. Every file states so in its own `notes` field, and the engine's test suite fails
 * if a fixture starts to look like a real record. Nothing here may be replaced with patient data —
 * see `docs/compliance/PRIVATE_DATA_WARNING.md`.
 */

import type { ClinicalExtraction } from "@workspace/contracts"

import case001 from "./case_001_knee.json"
import case002 from "./case_002_cardiology.json"
import case003 from "./case_003_dermatology.json"

export type SyntheticCase = {
  readonly id: string
  readonly label: string
  /** What this case exercises in the engine. Taken from the fixture's own `expected.json`. */
  readonly description: string
  readonly extraction: ClinicalExtraction
}

/**
 * TypeScript widens an imported JSON string to `string`, so a fixture cannot structurally satisfy
 * the literal unions in `ClinicalExtraction` (`sex: "m" | "w" | "d"`, `setting`, `severity`) without
 * a cast. This is the one place that cast happens, and it is not load-bearing: the engine validates
 * every extraction against the same schema and answers `422` naming the offending field, which the
 * review screen renders. A malformed fixture therefore surfaces as a visible validation error, not
 * as a wrong invoice.
 */
function asExtraction(fixture: unknown): ClinicalExtraction {
  return fixture as ClinicalExtraction
}

/**
 * Typed as a non-empty tuple so `SYNTHETIC_CASES[0]` is a `SyntheticCase` rather than
 * `SyntheticCase | undefined` under `noUncheckedIndexedAccess`.
 */
export const SYNTHETIC_CASES: readonly [SyntheticCase, ...SyntheticCase[]] = [
  {
    id: "case_001_knee",
    label: "Fall 001 · Knie (Orthopädie)",
    description:
      "Löst alle drei Verdrängungsregeln gleichzeitig aus (Spezifität, Zielleistung, wechselseitiger Ausschluss) und die Faktorleiter nach § 5 Abs. 2 GOÄ.",
    extraction: asExtraction(case001),
  },
  {
    id: "case_002_cardiology",
    label: "Fall 002 · Kardiologie",
    description:
      "Arbitrierung im EKG-Cluster (Nr. 650–653 schließen sich wechselseitig aus), Labor-Band nach § 5 Abs. 4 GOÄ und eine Begründung, die nur an eine Position gebunden ist.",
    extraction: asExtraction(case002),
  },
  {
    id: "case_003_dermatology",
    label: "Fall 003 · Dermatologie",
    description:
      "Analogansatz nach § 6 Abs. 2 GOÄ inklusive Kollisionsregel, damit eine Analogziffer nicht doppelt berechnet wird, plus § 5-Band für Abschnitt N.",
    extraction: asExtraction(case003),
  },
]

export function findSyntheticCase(id: string): SyntheticCase | undefined {
  return SYNTHETIC_CASES.find((entry) => entry.id === id)
}
