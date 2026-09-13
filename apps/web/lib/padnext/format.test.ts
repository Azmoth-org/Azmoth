import assert from "node:assert/strict"
import { test } from "node:test"

import {
  coverageFillPercent,
  coverageVerdictWidths,
  primaryBewertungText,
  verifiedDefectCodes,
} from "./format"

test("coverageFillPercent — 0.0 % ratio fills 0 % of the track", () => {
  assert.equal(coverageFillPercent(0, "1000.00"), 0)
})

test("coverageFillPercent — 15.0 % ratio fills 15 % of the track", () => {
  assert.equal(coverageFillPercent(0.15, "1000.00"), 15)
})

test("coverageFillPercent — 100.0 % ratio fills 100 % of the track", () => {
  assert.equal(coverageFillPercent(1, "1000.00"), 100)
})

test("coverageFillPercent — clamps a ratio below 0 or above 1", () => {
  assert.equal(coverageFillPercent(-0.2, "1000.00"), 0)
  assert.equal(coverageFillPercent(1.4, "1000.00"), 100)
})

test("coverageFillPercent — null ratio has no fill", () => {
  assert.equal(coverageFillPercent(null, "1000.00"), null)
  assert.equal(coverageFillPercent(undefined, "1000.00"), null)
  assert.equal(coverageFillPercent(Number.NaN, "1000.00"), null)
})

test("coverageFillPercent — no usable denominator has no fill, even at ratio 0", () => {
  assert.equal(coverageFillPercent(0, "0.00"), null)
  assert.equal(coverageFillPercent(0, null), null)
  assert.equal(coverageFillPercent(0, undefined), null)
  assert.equal(coverageFillPercent(0, "not-a-number"), null)
})

test("coverageVerdictWidths — splits the fill in proportion to each verdict's amount", () => {
  const widths = coverageVerdictWidths(
    { confirmed_wrong_eur: "300.00", confirmed_fine_eur: "700.00" },
    40
  )
  assert.equal(widths.wrong, 12) // 300/1000 of a 40 % fill
  assert.equal(widths.fine, 28) // 700/1000 of a 40 % fill
  assert.equal(widths.wrong + widths.fine, 40)
})

test("coverageVerdictWidths — both zero when neither verdict has an amount", () => {
  const widths = coverageVerdictWidths(
    { confirmed_wrong_eur: "0.00", confirmed_fine_eur: "0.00" },
    0
  )
  assert.deepEqual(widths, { wrong: 0, fine: 0 })
})

test("verifiedDefectCodes — pulls the codes out of a confirmed_wrong bucket_reason", () => {
  assert.deepEqual(
    verifiedDefectCodes(
      "Verifizierte Prüfung fehlgeschlagen: padnext_amount_mismatch, padnext_factor_above_maximum."
    ),
    ["padnext_amount_mismatch", "padnext_factor_above_maximum"]
  )
})

test("verifiedDefectCodes — a single code", () => {
  assert.deepEqual(
    verifiedDefectCodes("Verifizierte Prüfung fehlgeschlagen: padnext_justification_missing."),
    ["padnext_justification_missing"]
  )
})

test("verifiedDefectCodes — null for any other bucket_reason prose", () => {
  assert.equal(
    verifiedDefectCodes(
      "Die Regelprüfung hat diese Ziffer nicht bestätigt, aber auch keine verifizierte Regel " +
        "verletzt. Erfordert menschliche Prüfung."
    ),
    null
  )
  assert.equal(verifiedDefectCodes(""), null)
})

test("primaryBewertungText — translates every known code to its short German label", () => {
  assert.equal(
    primaryBewertungText(
      "Verifizierte Prüfung fehlgeschlagen: padnext_amount_mismatch, padnext_factor_above_maximum."
    ),
    "Betrag weicht von der Nachrechnung ab · Faktor über dem Höchstsatz"
  )
})

test("primaryBewertungText — falls back to the raw sentence when a code has no label", () => {
  const reason =
    "Verifizierte Prüfung fehlgeschlagen: padnext_amount_mismatch, padnext_some_future_code."
  assert.equal(primaryBewertungText(reason), reason)
})

test("primaryBewertungText — passes prose bucket_reason through unchanged", () => {
  const reason = "Alle anwendbaren Prüfungen bestanden; geprüft gegen verifizierte Regel(n) x."
  assert.equal(primaryBewertungText(reason), reason)
})
