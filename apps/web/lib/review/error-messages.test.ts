import assert from "node:assert/strict"
import { test } from "node:test"

import { GENERIC_MESSAGE, MESSAGES, messageFor } from "./error-messages"
import type { ReviewError } from "./types"

function error(overrides: Partial<ReviewError>): ReviewError {
  return { error: "something_unlisted", message: "irrelevant to rendering", ...overrides }
}

test("messageFor ignores error.message entirely — it is a lookup by code, not a passthrough", () => {
  // This is the property the review found missing: a backend improvement to `message` for a
  // code with no curated German sentence reaches nobody, because rendering never reads it.
  const withMessage = messageFor(error({ error: "unlisted_code", message: "some specific text" }))
  const withoutMessage = messageFor(error({ error: "unlisted_code", message: "" }))
  assert.equal(withMessage, GENERIC_MESSAGE)
  assert.equal(withMessage, withoutMessage)
})

test("an unlisted code falls through to GENERIC_MESSAGE", () => {
  assert.equal(messageFor(error({ error: "invalid_xml" })), GENERIC_MESSAGE)
  assert.equal(messageFor(error({ error: "padnext_unreadable" })), GENERIC_MESSAGE)
})

test("illegal_transition names all three ways a transition is refused, not just two", () => {
  // The regression this test guards: the sentence used to say "abgelehnter oder bereits
  // exportierter", which does not describe APPROVED -> APPROVED (a double-clicked approve
  // button) — the one transition refusal a reviewer is most likely to actually cause.
  const shown = messageFor(
    error({
      error: "illegal_transition",
      message:
        "Ein Vorschlag im Status „freigegeben“ kann nicht nach „freigegeben“ wechseln. " +
        "Aus „freigegeben“ ist möglich: exportiert.",
    })
  )
  assert.match(shown, /freigegeben/, "must mention the already-approved case")
  assert.match(shown, /abgelehnt/, "must still mention the already-rejected case")
  assert.match(shown, /exportiert/, "must still mention the already-exported case")
  assert.equal(shown, MESSAGES.illegal_transition)
})
