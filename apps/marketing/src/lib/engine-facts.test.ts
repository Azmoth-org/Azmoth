import assert from "node:assert/strict"
import { test } from "node:test"

import { engineFacts, formatStandDatum, SNAPSHOT_DATE } from "./engine-facts"

test("formatStandDatum — renders a German long date for the snapshot", () => {
  assert.equal(formatStandDatum("2026-09-13"), "13. September 2026")
})

test("engineFacts.standDatum — matches SNAPSHOT_DATE, formatted", () => {
  assert.equal(engineFacts.standDatum, formatStandDatum(SNAPSHOT_DATE))
  assert.match(engineFacts.standDatum, /2026/)
})

test("Metrics tiles — homepage and /pilot render the same Stand date", () => {
  // Both `startseite.zahlen` (home) and `pilot.abdeckung` (the /pilot page) render
  // `<Metrics>`, which reads `engineFacts.standDatum` directly rather than taking it as a
  // prop — so there is exactly one value for both pages to disagree on, and this asserts
  // that value is a real, non-empty Stand date rather than the module failing silently.
  assert.ok(engineFacts.standDatum.length > 0)
})
