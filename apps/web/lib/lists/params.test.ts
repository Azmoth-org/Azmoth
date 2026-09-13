import assert from "node:assert/strict"
import { test } from "node:test"

import { resultCountLabel } from "./params"

test("resultCountLabel — zero matches", () => {
  assert.equal(resultCountLabel(0), "Keine Prüfungen gefunden")
})

test("resultCountLabel — a negative total (defensive) reads the same as zero", () => {
  assert.equal(resultCountLabel(-1), "Keine Prüfungen gefunden")
})

test("resultCountLabel — exactly one match is singular", () => {
  assert.equal(resultCountLabel(1), "1 Prüfung gefunden")
})

test("resultCountLabel — more than one match is plural", () => {
  assert.equal(resultCountLabel(12), "12 Prüfungen gefunden")
})
