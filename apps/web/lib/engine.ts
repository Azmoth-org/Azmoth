/**
 * Server-side access to the engine. **Never imported by a client component.**
 *
 * `ENGINE_BASE_URL` stays server-only on purpose: it is not `NEXT_PUBLIC_`, so the browser never
 * learns where the engine lives and cannot reach it directly. Every call goes through a route
 * handler under `/api/engine/*`, which is also the seam where authentication will eventually sit —
 * there is none today (see `docs/compliance/PRIVATE_DATA_WARNING.md`).
 */

const DEFAULT_ENGINE_BASE_URL = "http://localhost:8000"

/** How long to wait on the engine. Above its own 5 s solver timeout, so a 504 comes from the engine. */
const ENGINE_TIMEOUT_MS = 30_000

export function engineBaseUrl(): string {
  return (process.env.ENGINE_BASE_URL ?? DEFAULT_ENGINE_BASE_URL).replace(/\/+$/, "")
}

/** A failure the browser can render. `status` is what the proxy route will answer with. */
export type EngineProxyFailure = {
  error: string
  message: string
  status: number
  details?: unknown
}

export type EngineProxyResult =
  | { ok: true; status: number; body: unknown }
  | { ok: false; failure: EngineProxyFailure }

/**
 * Forward one request to the engine and normalise every failure mode into something renderable.
 *
 * The engine's own error bodies are passed through untouched — they carry the field-level `422`
 * detail, the `504` timeout payload and the `409` illegal-transition payload that the UI shows.
 */
export async function callEngine(
  path: string,
  init?: { method?: "GET" | "POST"; body?: unknown },
): Promise<EngineProxyResult> {
  const url = `${engineBaseUrl()}${path}`
  const method = init?.method ?? "GET"

  let response: Response
  try {
    response = await fetch(url, {
      method,
      headers: init?.body === undefined ? undefined : { "Content-Type": "application/json" },
      body: init?.body === undefined ? undefined : JSON.stringify(init.body),
      // A billing draft must never be served from a cache the UI does not control.
      cache: "no-store",
      signal: AbortSignal.timeout(ENGINE_TIMEOUT_MS),
    })
  } catch (cause) {
    const timedOut = cause instanceof Error && cause.name === "TimeoutError"
    return {
      ok: false,
      failure: {
        error: timedOut ? "engine_unreachable_timeout" : "engine_unreachable",
        message: timedOut
          ? `Die Engine hat innerhalb von ${ENGINE_TIMEOUT_MS / 1000} s nicht geantwortet.`
          : "Die Engine ist nicht erreichbar. Läuft sie auf ENGINE_BASE_URL?",
        status: 503,
        details: { url, method, cause: cause instanceof Error ? cause.message : String(cause) },
      },
    }
  }

  const raw = await response.text()

  if (raw.length === 0) {
    // A 200 with no body is the one case the UI cannot render at all, so it is named rather than
    // handed to JSON.parse and surfaced as a syntax error.
    return {
      ok: false,
      failure: {
        error: "empty_response",
        message: `Die Engine hat mit HTTP ${response.status} und leerem Body geantwortet.`,
        status: 502,
        details: { url, method, status: response.status },
      },
    }
  }

  let body: unknown
  try {
    body = JSON.parse(raw)
  } catch {
    return {
      ok: false,
      failure: {
        error: "unparsable_response",
        message: "Die Antwort der Engine ist kein gültiges JSON.",
        status: 502,
        details: { url, method, status: response.status, raw: raw.slice(0, 4000) },
      },
    }
  }

  return { ok: true, status: response.status, body }
}

/** Turn an `EngineProxyResult` into the route handler's response. */
export function proxyResponse(result: EngineProxyResult): Response {
  if (result.ok) {
    return Response.json(result.body, { status: result.status })
  }
  const { status, ...failure } = result.failure
  return Response.json(failure, { status })
}
