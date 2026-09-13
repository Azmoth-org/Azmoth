import assert from "node:assert/strict"
import { test } from "node:test"

import { activeSectionId } from "./section-nav"

const OFFSETS = [
  { id: "bewertung", top: 100 },
  { id: "meta", top: 800 },
  { id: "positionen", top: 1600 },
  { id: "befunde", top: 3200 },
]

test("activeSectionId — null before any section has been reached", () => {
  assert.equal(activeSectionId(OFFSETS, 0), null)
  assert.equal(activeSectionId(OFFSETS, 50), null)
})

test("activeSectionId — the last section whose top is at or before scrollY", () => {
  assert.equal(activeSectionId(OFFSETS, 100), "bewertung")
  assert.equal(activeSectionId(OFFSETS, 799), "bewertung")
  assert.equal(activeSectionId(OFFSETS, 800), "meta")
  assert.equal(activeSectionId(OFFSETS, 2000), "positionen")
  assert.equal(activeSectionId(OFFSETS, 5000), "befunde")
})

test("activeSectionId — a threshold shifts the reach point earlier", () => {
  // With 100px of headroom (the sticky nav's own height), a section 100px below scrollY already
  // counts as reached — the reader has scrolled its heading up under the nav, not past it.
  assert.equal(activeSectionId(OFFSETS, 700, 100), "meta")
  assert.equal(activeSectionId(OFFSETS, 699, 100), "bewertung")
})

test("activeSectionId — works regardless of how many sections exist", () => {
  assert.equal(activeSectionId([{ id: "only", top: 0 }], 500), "only")
  assert.equal(activeSectionId([], 500), null)
})
