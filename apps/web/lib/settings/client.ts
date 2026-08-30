/**
 * Browser-side calls to the settings proxy: API keys, and what they have consumed.
 *
 * Same contract as every other client here — never throws, never returns a half-parsed body. The
 * screen renders either data whose fields it can trust, or a named error with the raw details.
 *
 * Every shape resolves into `@workspace/contracts`, generated from the engine's own OpenAPI
 * document, so nothing is duplicated and a field renamed in the engine breaks a build rather than
 * a screen.
 *
 * **One rule is specific to this module: the minted token is never stored.** `mintApiKey` returns
 * it to exactly one caller, which puts it on screen and holds it in React state until the dialog
 * closes. It is not written to `localStorage`, not put in a URL, and not logged — the engine keeps
 * only a SHA-256 hash, so anything that persisted it here would become the only copy in existence
 * and the least protected one.
 */

import type {
  ApiKeyIssued,
  ApiKeyList,
  ApiKeyRevoked,
  UsageSummary,
} from "@workspace/contracts"

import { toReviewError, type ReviewError } from "@/lib/review/types"

export type { ApiKeyIssued, ApiKeyList, ApiKeyRevoked, UsageSummary }
export type { ReviewError }

export type ApiKeyListResult =
  | { kind: "keys"; keys: ApiKeyList }
  | { kind: "error"; error: ReviewError }

export type MintResult =
  | { kind: "minted"; key: ApiKeyIssued }
  | { kind: "error"; error: ReviewError }

export type RevokeResult =
  | { kind: "revoked"; result: ApiKeyRevoked }
  | { kind: "error"; error: ReviewError }

export type UsageResult =
  | { kind: "usage"; usage: UsageSummary }
  | { kind: "error"; error: ReviewError }

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

async function readJson(
  response: Response
): Promise<{ ok: true; body: unknown } | { ok: false; error: ReviewError }> {
  const raw = await response.text()

  if (raw.length === 0) {
    return {
      ok: false,
      error: {
        error: "empty_response",
        message: `Leere Antwort (HTTP ${response.status}).`,
        status: response.status,
      },
    }
  }

  let body: unknown
  try {
    body = JSON.parse(raw)
  } catch {
    return {
      ok: false,
      error: {
        error: "unparsable_response",
        message: "Die Antwort ist kein gültiges JSON.",
        status: response.status,
        details: raw.slice(0, 4000),
      },
    }
  }

  if (!response.ok)
    return { ok: false, error: toReviewError(response.status, body) }
  return { ok: true, body }
}

function unreachable(cause: unknown): { kind: "error"; error: ReviewError } {
  return {
    kind: "error",
    error: {
      error: "proxy_unreachable",
      message:
        "Die Anfrage an /api/engine konnte nicht gesendet werden. Läuft der Next.js-Server noch?",
      details: cause instanceof Error ? cause.message : String(cause),
    },
  }
}

function skew(
  status: number,
  body: unknown,
  what: string
): { kind: "error"; error: ReviewError } {
  return {
    kind: "error",
    error: {
      error: "unexpected_response_shape",
      message:
        `Die Engine hat geantwortet, aber der Body enthält ${what}. Möglicherweise laufen ` +
        "Engine und UI auf verschiedenen Contract-Versionen — packages/contracts neu generieren.",
      status,
      details: body,
    },
  }
}

/**
 * The one shape check that has real consequences.
 *
 * A mint response without `token` cannot be rendered *and cannot be recovered*: the key exists in
 * the database, the caller will never see it, and they now hold an unusable row they have to find
 * and revoke. So it is checked explicitly and reported as version skew rather than shown as an
 * empty field somebody copies.
 */
function isIssuedShape(value: unknown): value is ApiKeyIssued {
  return (
    isRecord(value) &&
    typeof value.token === "string" &&
    value.token.length > 0 &&
    typeof value.key_id === "string"
  )
}

function isKeyListShape(value: unknown): value is ApiKeyList {
  return isRecord(value) && Array.isArray(value.keys)
}

function isUsageShape(value: unknown): value is UsageSummary {
  return (
    isRecord(value) &&
    typeof value.total_requests === "number" &&
    typeof value.total_bytes_processed === "number" &&
    Array.isArray(value.by_endpoint) &&
    Array.isArray(value.by_key)
  )
}

export async function fetchApiKeys(
  signal?: AbortSignal
): Promise<ApiKeyListResult> {
  let response: Response
  try {
    response = await fetch("/api/engine/settings/api-keys", {
      cache: "no-store",
      signal,
    })
  } catch (cause) {
    return unreachable(cause)
  }

  const parsed = await readJson(response)
  if (!parsed.ok) return { kind: "error", error: parsed.error }
  if (!isKeyListShape(parsed.body))
    return skew(response.status, parsed.body, "keine Schlüsselliste")
  return { kind: "keys", keys: parsed.body }
}

/**
 * Mint a key. **The response carries the only copy of the secret that will ever exist.**
 *
 * The caller must render it immediately. Nothing here retries: a retry on an ambiguous failure —
 * a timeout after the engine committed — would mint a second live key that nobody has seen, which
 * is a credential in existence with no owner.
 */
export async function mintApiKey(name: string): Promise<MintResult> {
  let response: Response
  try {
    response = await fetch("/api/engine/settings/api-keys", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: name.trim() }),
      cache: "no-store",
    })
  } catch (cause) {
    return unreachable(cause)
  }

  const parsed = await readJson(response)
  if (!parsed.ok) return { kind: "error", error: parsed.error }
  if (!isIssuedShape(parsed.body))
    return skew(response.status, parsed.body, "keinen Schlüssel")
  return { kind: "minted", key: parsed.body }
}

export async function revokeApiKey(keyId: string): Promise<RevokeResult> {
  let response: Response
  try {
    response = await fetch(
      `/api/engine/settings/api-keys/${encodeURIComponent(keyId)}`,
      { method: "DELETE", cache: "no-store" }
    )
  } catch (cause) {
    return unreachable(cause)
  }

  const parsed = await readJson(response)
  if (!parsed.ok) return { kind: "error", error: parsed.error }
  if (!isRecord(parsed.body) || typeof parsed.body.key_id !== "string")
    return skew(response.status, parsed.body, "keine Bestätigung")
  return { kind: "revoked", result: parsed.body as ApiKeyRevoked }
}

export async function fetchUsage(signal?: AbortSignal): Promise<UsageResult> {
  let response: Response
  try {
    response = await fetch("/api/engine/settings/usage", {
      cache: "no-store",
      signal,
    })
  } catch (cause) {
    return unreachable(cause)
  }

  const parsed = await readJson(response)
  if (!parsed.ok) return { kind: "error", error: parsed.error }
  if (!isUsageShape(parsed.body))
    return skew(response.status, parsed.body, "keine Verbrauchsübersicht")
  return { kind: "usage", usage: parsed.body }
}
