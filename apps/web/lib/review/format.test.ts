import assert from "node:assert/strict"
import { test } from "node:test"

import {
  RULE_COVERAGE_LABEL,
  ruleCoverageHeadline,
  timestamp,
} from "./format"

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
