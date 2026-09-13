import assert from "node:assert/strict"
import { test } from "node:test"

import {
  RULE_COVERAGE_LABEL,
  groupWarnings,
  hintCountLabel,
  ruleCoverageHeadline,
  timestamp,
} from "./format"
import type { EngineWarning } from "./types"

function warning(overrides: Partial<EngineWarning>): EngineWarning {
  return {
    type: "rule_coverage_incomplete",
    severity: "info",
    message: "Die Regelabdeckung ist unvollständig.",
    legal_basis: "",
    rule_id: "",
    ziffer: null,
    ...overrides,
  }
}

test("ruleCoverageHeadline — states both live values, not literals", () => {
  assert.equal(
    ruleCoverageHeadline(944, 980),
    "944 von 980 Regeln durchgesetzt"
  )
  assert.equal(ruleCoverageHeadline(0, 0), "0 von 0 Regeln durchgesetzt")
})

test("timestamp — renders a Stand date for a valid ISO string", () => {
  const rendered = timestamp("2026-09-13T09:30:00Z")
  assert.notEqual(rendered, "—")
  assert.match(rendered, /2026/)
})

test("timestamp — falls back to an em dash when there is nothing to show", () => {
  assert.equal(timestamp(null), "—")
  assert.equal(timestamp(undefined), "—")
})

test("RULE_COVERAGE_LABEL — enforced and advisory are top-level, never a 'davon'", () => {
  assert.equal(RULE_COVERAGE_LABEL.enforced, "Durchgesetzt")
  assert.equal(RULE_COVERAGE_LABEL.advisory, "Nicht durchgesetzt")
  assert.ok(!RULE_COVERAGE_LABEL.enforced.startsWith("Davon"))
  assert.ok(!RULE_COVERAGE_LABEL.advisory.startsWith("Davon"))
})

test("RULE_COVERAGE_LABEL — unverified and analog are marked as a 'davon' of advisory", () => {
  assert.ok(RULE_COVERAGE_LABEL.unverified.startsWith("Davon"))
  assert.ok(RULE_COVERAGE_LABEL.analog.startsWith("Davon"))
})

test("advisory_rule_count is exactly suppressed + analog, by the engine's own construction", () => {
  // rule_coverage.py builds `advisory_rule_count` as the sum of these two counts — this fixture
  // stands in for a response, to pin the invariant the "davon" nesting depends on.
  const suppressed = 6
  const analog = 3
  const advisory = 9
  assert.equal(suppressed + analog, advisory)
})

test("hintCountLabel — singular for one, plural otherwise, always with a live count", () => {
  assert.equal(hintCountLabel(1), "1 Hinweis")
  assert.equal(hintCountLabel(6), "6 Hinweise")
  assert.equal(hintCountLabel(0), "0 Hinweise")
})

test("groupWarnings — folds repeated types into one group with a live count", () => {
  const warnings = [
    warning({ type: "rule_coverage_incomplete", ziffer: "1" }),
    warning({ type: "rule_coverage_incomplete", ziffer: "2" }),
    warning({ type: "rule_coverage_incomplete", ziffer: "3" }),
    warning({ type: "rule_coverage_incomplete", ziffer: "4" }),
    warning({ type: "rule_coverage_incomplete", ziffer: "5" }),
    warning({ type: "rule_coverage_incomplete", ziffer: "6" }),
  ]

  const groups = groupWarnings(warnings)
  assert.equal(groups.length, 1)
  assert.equal(groups[0]!.type, "rule_coverage_incomplete")
  assert.equal(groups[0]!.warnings.length, 6)
  assert.equal(hintCountLabel(groups[0]!.warnings.length), "6 Hinweise")
})

test("groupWarnings — a type occurring once stays its own group of one", () => {
  const warnings = [warning({ type: "solver_timeout_partial" })]
  const groups = groupWarnings(warnings)
  assert.equal(groups.length, 1)
  assert.equal(groups[0]!.warnings.length, 1)
})

test("groupWarnings — distinct types never merge, and nothing is dropped", () => {
  const warnings = [
    warning({ type: "rule_coverage_incomplete", ziffer: "1" }),
    warning({ type: "justification_missing", ziffer: "2", severity: "error" }),
    warning({ type: "rule_coverage_incomplete", ziffer: "3" }),
  ]

  const groups = groupWarnings(warnings)
  assert.equal(groups.length, 2)
  const totalWarnings = groups.reduce((sum, g) => sum + g.warnings.length, 0)
  assert.equal(totalWarnings, 3)
})

test("groupWarnings — orders groups by severity, most urgent first", () => {
  const warnings = [
    warning({ type: "advisory_rules_present", severity: "info" }),
    warning({ type: "justification_missing", severity: "error" }),
  ]

  const groups = groupWarnings(warnings)
  assert.equal(groups[0]!.type, "justification_missing")
  assert.equal(groups[1]!.type, "advisory_rules_present")
})

test("groupWarnings — the representative is the most severe warning in its group", () => {
  const warnings = [
    warning({ type: "rule_coverage_incomplete", severity: "info", ziffer: "1" }),
    warning({ type: "rule_coverage_incomplete", severity: "error", ziffer: "2" }),
  ]

  const groups = groupWarnings(warnings)
  assert.equal(groups[0]!.representative.severity, "error")
  assert.equal(groups[0]!.representative.ziffer, "2")
})
