import assert from "node:assert/strict"
import { test } from "node:test"

import { pruefenButtonState } from "./upload-state"

test("no file selected — disabled, asks the reader to choose one", () => {
  const state = pruefenButtonState({ hasFile: false, confirmed: false, pending: false })
  assert.equal(state.disabled, true)
  assert.equal(state.reason, "Bitte PADnext-Datei auswählen.")
})

test("file selected but anonymisation not confirmed — disabled, asks for the confirmation", () => {
  const state = pruefenButtonState({ hasFile: true, confirmed: false, pending: false })
  assert.equal(state.disabled, true)
  assert.equal(state.reason, "Bitte Anonymisierung bestätigen.")
})

test("file selected and confirmed — enabled, no reason to show", () => {
  const state = pruefenButtonState({ hasFile: true, confirmed: true, pending: false })
  assert.equal(state.disabled, false)
  assert.equal(state.reason, null)
})

test("pending — disabled regardless of file or confirmation, no reason (the spinner says it)", () => {
  assert.equal(
    pruefenButtonState({ hasFile: true, confirmed: true, pending: true }).reason,
    null
  )
  assert.equal(
    pruefenButtonState({ hasFile: false, confirmed: false, pending: true }).disabled,
    true
  )
})
