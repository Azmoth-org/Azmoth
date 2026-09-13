import assert from "node:assert/strict"
import { test } from "node:test"

import { proofLineCountLabel } from "./proof-dialog"

test("proofLineCountLabel — singular for one, plural otherwise, always with a live count", () => {
  assert.equal(proofLineCountLabel(1), "1 Beweiszeile")
  assert.equal(proofLineCountLabel(6), "6 Beweiszeilen")
  assert.equal(proofLineCountLabel(0), "0 Beweiszeilen")
})
