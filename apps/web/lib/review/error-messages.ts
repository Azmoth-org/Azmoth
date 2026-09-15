import type { ReviewError } from "@/lib/review/types"

/** The sentence shown for anything not named in `MESSAGES`, and for anything with no useful advice. */
export const GENERIC_MESSAGE =
  "Ein technischer Fehler ist aufgetreten. Bitte versuchen Sie es erneut oder " +
  "kontaktieren Sie den Support."

/**
 * What each failure means to the person who hit it. German, specific, and actionable or silent.
 *
 * Every entry here is a promise that the reader can do something with the sentence. A failure whose
 * only honest description is "our software broke" is deliberately absent and falls through to
 * `GENERIC_MESSAGE` — an entry that restates the error code in longer words is worse than no entry,
 * because it costs the reader the time to find out it says nothing.
 *
 * See `lib/review/error-messages.test.ts` for the case this module exists to keep true:
 * `illegal_transition` used to describe only "abgelehnt oder exportiert", which is not the
 * situation a double-clicked approve button actually produces (`APPROVED` → `APPROVED`) — the
 * reader saw a sentence that named two states that were not theirs.
 */
export const MESSAGES: Record<string, string> = {
  // Infrastructure. The reader cannot fix any of these and must not be told to try; what they can
  // do is wait or call us, and that is what these say.
  engine_unreachable:
    "Der Prüfdienst ist zurzeit nicht erreichbar. Bitte versuchen Sie es in einigen Minuten " +
    "erneut — falls das Problem bestehen bleibt, kontaktieren Sie den Support.",
  engine_unreachable_timeout:
    "Der Prüfdienst antwortet zurzeit nicht. Bitte versuchen Sie es in einigen Minuten erneut — " +
    "falls das Problem bestehen bleibt, kontaktieren Sie den Support.",
  proxy_unreachable:
    "Die Verbindung zum Server ist unterbrochen. Bitte prüfen Sie Ihre Internetverbindung und " +
    "laden Sie die Seite neu.",
  rules_engine_failed: GENERIC_MESSAGE,
  validation_failed: GENERIC_MESSAGE,
  empty_response: GENERIC_MESSAGE,
  unparsable_response: GENERIC_MESSAGE,
  unexpected_response_shape: GENERIC_MESSAGE,

  // The solver gave up. Worth its own sentence because the *absence* of a draft is deliberate here
  // and a reader who is not told that will read it as a lost result.
  solver_timeout:
    "Die Prüfung hat zu lange gedauert und wurde abgebrochen. Es wird bewusst kein " +
    "unvollständiger Entwurf ausgegeben. Bitte versuchen Sie es erneut oder prüfen Sie die " +
    "Rechnung in kleineren Teilen.",

  // The reader's own input or their own workflow. These are the ones where a specific sentence
  // actually saves them something.
  validation_error:
    "Die hochgeladene Datei entspricht nicht dem erwarteten Format. Bitte prüfen Sie die Datei " +
    "und laden Sie sie erneut hoch.",
  // Covers all three ways a transition can be refused: a draft that was already decided
  // (approved or rejected) and a proposal that was already exported. Naming only two of the
  // three used to leave the most common case — a double-clicked approve button, APPROVED →
  // APPROVED — reading a sentence about rejection and export that did not describe it.
  illegal_transition:
    "Dieser Schritt ist für den aktuellen Status nicht möglich. Ein bereits freigegebener, " +
    "abgelehnter oder bereits exportierter Vorschlag kann nicht erneut entschieden werden, und " +
    "ein Export ist nur einmal möglich.",
  proposal_not_found:
    "Unter dieser Adresse ist kein Vorschlag gespeichert. Bitte prüfen Sie den Link oder suchen " +
    "Sie den Vorschlag über „Alle Prüfungen“.",
  malformed_proposal_id:
    "Der Link ist unvollständig. Bitte öffnen Sie den Vorschlag über „Alle Prüfungen“.",
  malformed_batch_id:
    "Der Link ist unvollständig. Bitte öffnen Sie den Stapel über die Stapel-Historie.",
  batch_not_found:
    "Unter dieser Adresse ist kein Stapel gespeichert. Bitte prüfen Sie den Link oder laden Sie " +
    "die Dateien erneut hoch.",
  batch_not_completed:
    "Der Stapel ist noch nicht vollständig geprüft. Der Export ist erst möglich, wenn alle " +
    "Dateien abgeschlossen sind.",
  unreadable_request_body:
    "Für den Export wird ein Name benötigt. Bitte tragen Sie ein, wer den Export vornimmt.",
  no_active_organization:
    "Diese Sitzung ist keiner Praxis zugeordnet. Bitte wählen Sie oben links eine Organisation " +
    "aus oder legen Sie eine an.",
  unauthenticated: "Ihre Sitzung ist abgelaufen. Bitte melden Sie sich erneut an.",
}

/** The sentence `ErrorPanel` shows for one failure. */
export function messageFor(error: ReviewError): string {
  return MESSAGES[error.error] ?? GENERIC_MESSAGE
}
