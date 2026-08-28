/**
 * Server-side access to the engine. **Never imported by a client component.**
 *
 * `ENGINE_BASE_URL` stays server-only on purpose: it is not `NEXT_PUBLIC_`, so the browser never
 * learns where the engine lives and cannot reach it directly. Every call goes through a route
 * handler under `/api/engine/*`, and that is the seam authentication sits in: `middleware.ts`
 * refuses those routes without a session, and every function here forwards the resulting user id to
 * the engine so its audit log can name a person.
 *
 * ## The session is resolved here, and a call without one is refused here
 *
 * There are four ways out of this module — JSON, raw bytes, multipart and a file download — and
 * they are used by a dozen route handlers. Neither half of what the session is for can be left to
 * the call site: a `X-User-ID` header attached per handler is one somebody forgets, and the failure
 * is silent (the request succeeds and the audit row says `anonymous`); an access check written per
 * handler is one somebody forgets, and *that* failure is a proposal served to whoever asked. So
 * `requireIdentity()` is called by all four, and both properties belong to *talking to the engine*
 * rather than to remembering to.
 *
 * ## Two headers, and only one of them is optional
 *
 * `X-User-ID` says **who** — the engine records it in its audit log and accepts a call without it,
 * attributing the row to `anonymous`. `X-Organization-ID` says **whose data**, and the engine
 * refuses a proposal or batch call that does not carry it with a `403`. Every proposal and batch row
 * is stamped with it on write and filtered by it on read, so one practice cannot list, open, approve
 * or export another's records — see `apps/engine/app/api/tenancy.py`.
 *
 * The value is the session's `activeOrganizationId`: the Better Auth `organization()` plugin's own
 * field on the session row, which is what the rail's switcher writes when a reader changes practice.
 * Taking it from the session rather than from a parameter is the whole security property. A tenant
 * a caller could *pass* is a tenant a caller could *choose*, and this module is reached from route
 * handlers whose input is a URL the browser controls — so an organisation id in a query string
 * would be an endpoint for reading any practice's drafts by guessing its id. The session is the one
 * place the value can come from that the browser cannot set.
 *
 * A session with no active organisation is refused **here**, with a sentence that says what to do,
 * rather than by sending no header and letting the engine answer `403` with a message about a
 * header the reader has never heard of. It should not happen — onboarding creates the practice and
 * makes it active, and `middleware.ts` sends a session that has not onboarded there first — but "it
 * should not happen" is not a reason to render an incomprehensible error when it does.
 *
 * This is the authoritative check. `middleware.ts` refuses `/api/engine/*` without a session cookie
 * and cannot do better — it has no database and cannot verify one — so a cookie that is present but
 * forged, expired or **revoked by a sign-out** gets past it. It does not get past here: this
 * resolves the token against the `session` table, and a `null` answer is a 401 rather than a proxied
 * request. Without this, signing out would stop the screens rendering while leaving the data behind
 * them readable to a replayed cookie.
 *
 * Only the id travels to the engine. Not the name, not the address: the engine writes what it is
 * given into an append-only log on a service that handles clinical data, and a record that by
 * construction cannot be corrected or deleted is the wrong place to put a person's contact details.
 * The id resolves to them through Better Auth's own `user` table, in the same database.
 *
 * The engine does not verify the header, and `apps/engine/app/api/identity.py` says so at length.
 * What makes it trustworthy is the deployment shape — the engine is not published to the browser,
 * and this proxy is its only caller — together with the fact that nothing reaches the engine from
 * here without a session that was checked against the database first. A Bearer token the engine
 * verifies itself is the next step, and `requireIdentity` is where it goes.
 */

import { headers } from "next/headers"

import { getAuth } from "@/lib/auth"

const DEFAULT_ENGINE_BASE_URL = "http://localhost:8000"

/** The header name the engine reads. Must match `USER_ID_HEADER` in `app/api/identity.py`. */
const USER_ID_HEADER = "X-User-ID"

/**
 * The tenant header. Must match `ORGANIZATION_ID_HEADER` in `app/api/tenancy.py`.
 *
 * Sent on every call this module makes, including the ones the engine does not scope
 * (`POST /padnext/audit` stores nothing, and `GET /health` describes the process). Attaching it
 * centrally rather than per endpoint is the point: a list of "which calls need the tenant" is a list
 * that goes stale the first time an endpoint starts storing something, and the failure mode is a
 * `403` in production rather than a compile error.
 */
const ORGANIZATION_ID_HEADER = "X-Organization-ID"

/** What the caller must have before anything is proxied: a session the database recognises. */
type Identity =
  | { ok: true; headers: Record<string, string> }
  | { ok: false; failure: EngineProxyFailure }

/**
 * The signed-in caller's identity headers, or the 401 to answer with.
 *
 * The message is German and says what to do about it, because it is rendered: a session can expire
 * while a reviewer has `/review` open, and the next action they take lands here.
 */
async function requireIdentity(): Promise<Identity> {
  const session = await getAuth().api.getSession({ headers: await headers() })
  if (!session) {
    return {
      ok: false,
      failure: {
        error: "unauthenticated",
        message: "Die Sitzung ist abgelaufen. Bitte melden Sie sich erneut an.",
        status: 401,
      },
    }
  }

  const organizationId = session.session.activeOrganizationId
  if (!organizationId) {
    // A `403`, matching what the engine would answer, so a caller switching on the status sees one
    // meaning for one condition. The message is German and actionable because it is rendered: this
    // is reachable by a reader whose only organisation was deleted while they were signed in.
    return {
      ok: false,
      failure: {
        error: "no_active_organization",
        message:
          "Diese Sitzung ist keiner Praxis zugeordnet. Wählen Sie oben links eine Organisation " +
          "aus oder legen Sie eine an — Vorschläge und Stapel gehören immer zu genau einer Praxis.",
        status: 403,
      },
    }
  }

  return {
    ok: true,
    headers: {
      [USER_ID_HEADER]: session.user.id,
      [ORGANIZATION_ID_HEADER]: organizationId,
    },
  }
}

/** How long to wait on the engine. Above its own 5 s solver timeout, so a 504 comes from the engine. */
const ENGINE_TIMEOUT_MS = 30_000

export function engineBaseUrl(): string {
  return (process.env.ENGINE_BASE_URL ?? DEFAULT_ENGINE_BASE_URL).replace(
    /\/+$/,
    ""
  )
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
  init?: { method?: "GET" | "POST"; body?: unknown }
): Promise<EngineProxyResult> {
  const url = `${engineBaseUrl()}${path}`
  const method = init?.method ?? "GET"

  const identity = await requireIdentity()
  if (!identity.ok) return { ok: false, failure: identity.failure }

  let response: Response
  try {
    response = await fetch(url, {
      method,
      headers: {
        ...identity.headers,
        ...(init?.body === undefined
          ? {}
          : { "Content-Type": "application/json" }),
      },
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
        details: {
          url,
          method,
          cause: cause instanceof Error ? cause.message : String(cause),
        },
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
        details: {
          url,
          method,
          status: response.status,
          raw: raw.slice(0, 4000),
        },
      },
    }
  }

  return { ok: true, status: response.status, body }
}

/**
 * Forward one request whose body is a *file* rather than JSON.
 *
 * `POST /api/v1/padnext/audit` takes the PADnext delivery itself as raw bytes — a `.padx` container
 * or a bare `*_padx.xml` payload — so it cannot go through `callEngine`, which JSON-encodes. The
 * bytes are passed through untouched; re-encoding them would break the container's ZIP magic and
 * change the receipt hash the engine computes over the file.
 *
 * `filename` travels in `x-padnext-filename` because the engine uses it only for the audit trail,
 * and a filename is not a place to put a patient's name: the engine parses no identity out of it,
 * and the upload is synthetic data only.
 */
export async function callEngineBytes(
  path: string,
  {
    body,
    filename,
    contentType,
  }: { body: ArrayBuffer; filename?: string; contentType?: string }
): Promise<EngineProxyResult> {
  const url = `${engineBaseUrl()}${path}`
  const identity = await requireIdentity()
  if (!identity.ok) return { ok: false, failure: identity.failure }

  let response: Response
  try {
    response = await fetch(url, {
      method: "POST",
      headers: {
        ...identity.headers,
        "Content-Type": contentType ?? "application/octet-stream",
        ...(filename ? { "x-padnext-filename": filename } : {}),
      },
      body,
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
        details: {
          url,
          method: "POST",
          cause: cause instanceof Error ? cause.message : String(cause),
        },
      },
    }
  }

  const raw = await response.text()

  if (raw.length === 0) {
    return {
      ok: false,
      failure: {
        error: "empty_response",
        message: `Die Engine hat mit HTTP ${response.status} und leerem Body geantwortet.`,
        status: 502,
        details: { url, method: "POST", status: response.status },
      },
    }
  }

  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    return {
      ok: false,
      failure: {
        error: "unparsable_response",
        message: "Die Antwort der Engine ist kein gültiges JSON.",
        status: 502,
        details: {
          url,
          method: "POST",
          status: response.status,
          raw: raw.slice(0, 4000),
        },
      },
    }
  }

  return { ok: true, status: response.status, body: parsed }
}

/**
 * Forward one `multipart/form-data` request, body and boundary untouched.
 *
 * `POST /api/v1/padnext/batch` takes many files in one request, which is what multipart is for and
 * the reason the engine now depends on `python-multipart`. The body is streamed through as the
 * `FormData` the route handler parsed: re-encoding the parts would generate a new boundary and, on
 * a `.padx` container, risk mangling the ZIP bytes the engine sniffs by magic number.
 *
 * `BATCH_TIMEOUT_MS` is longer than `ENGINE_TIMEOUT_MS` and is NOT the batch's own budget. It
 * covers the *upload* only: a hundred deliveries is a lot of bytes to push, but the endpoint
 * answers `202` as soon as the rows are written, because the audit happens in a background task
 * the client polls for. Nothing here waits for a batch to finish.
 */
const BATCH_TIMEOUT_MS = 120_000

export async function callEngineFormData(
  path: string,
  form: FormData
): Promise<EngineProxyResult> {
  const url = `${engineBaseUrl()}${path}`
  const identity = await requireIdentity()
  if (!identity.ok) return { ok: false, failure: identity.failure }

  let response: Response
  try {
    response = await fetch(url, {
      method: "POST",
      // No Content-Type header: `fetch` sets it from the FormData, including the boundary. Setting
      // it by hand is the classic way to send a multipart body the far end cannot split. The
      // identity headers are safe to set here for the same reason: they name one header, not that one.
      headers: identity.headers,
      body: form,
      cache: "no-store",
      signal: AbortSignal.timeout(BATCH_TIMEOUT_MS),
    })
  } catch (cause) {
    const timedOut = cause instanceof Error && cause.name === "TimeoutError"
    return {
      ok: false,
      failure: {
        error: timedOut ? "engine_unreachable_timeout" : "engine_unreachable",
        message: timedOut
          ? `Die Engine hat den Upload innerhalb von ${BATCH_TIMEOUT_MS / 1000} s nicht angenommen.`
          : "Die Engine ist nicht erreichbar. Läuft sie auf ENGINE_BASE_URL?",
        status: 503,
        details: {
          url,
          method: "POST",
          cause: cause instanceof Error ? cause.message : String(cause),
        },
      },
    }
  }

  const raw = await response.text()

  if (raw.length === 0) {
    return {
      ok: false,
      failure: {
        error: "empty_response",
        message: `Die Engine hat mit HTTP ${response.status} und leerem Body geantwortet.`,
        status: 502,
        details: { url, method: "POST", status: response.status },
      },
    }
  }

  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    return {
      ok: false,
      failure: {
        error: "unparsable_response",
        message: "Die Antwort der Engine ist kein gültiges JSON.",
        status: 502,
        details: {
          url,
          method: "POST",
          status: response.status,
          raw: raw.slice(0, 4000),
        },
      },
    }
  }

  return { ok: true, status: response.status, body: parsed }
}

/**
 * Forward a request whose *successful* response is a file, and hand the bytes straight back.
 *
 * The two export endpoints answer with an attachment — a JSON document or a ZIP — and with a JSON
 * error body when they refuse. So this returns a `Response` rather than an `EngineProxyResult`:
 * there is nothing useful for the proxy to parse on the happy path, and re-encoding the bytes
 * would break the ZIP.
 *
 * `Content-Disposition` is forwarded because it carries the filename the engine chose, and the
 * browser needs it to save the file under a name that means something. `Content-Type` is forwarded
 * for the same reason. Nothing else is: response headers from an upstream service are not something
 * to relay wholesale.
 *
 * A refusal (409, 404, 422) comes back as its own JSON body with its own status, untouched, so the
 * screen renders the engine's actual reason rather than a generic "download failed".
 */
export async function proxyEngineDownload(
  path: string,
  init?: { method?: "GET" | "POST"; body?: unknown }
): Promise<Response> {
  const url = `${engineBaseUrl()}${path}`
  const method = init?.method ?? "POST"
  const identity = await requireIdentity()
  if (!identity.ok) {
    // A `Response`, not an `EngineProxyResult`: this function's contract is bytes-or-refusal, so
    // the refusal has to be shaped like every other one it can produce.
    const { status, ...failure } = identity.failure
    return Response.json(failure, { status })
  }

  let response: Response
  try {
    response = await fetch(url, {
      method,
      headers: {
        ...identity.headers,
        ...(init?.body === undefined
          ? {}
          : { "Content-Type": "application/json" }),
      },
      body: init?.body === undefined ? undefined : JSON.stringify(init.body),
      cache: "no-store",
      // Above `ENGINE_TIMEOUT_MS`: a batch export renders every position of every file in the
      // batch into CSV, which for a few hundred invoices is real work.
      signal: AbortSignal.timeout(60_000),
    })
  } catch (cause) {
    const timedOut = cause instanceof Error && cause.name === "TimeoutError"
    return Response.json(
      {
        error: timedOut ? "engine_unreachable_timeout" : "engine_unreachable",
        message: timedOut
          ? "Die Engine hat den Export nicht innerhalb von 60 s geliefert."
          : "Die Engine ist nicht erreichbar. Läuft sie auf ENGINE_BASE_URL?",
        details: {
          url,
          method,
          cause: cause instanceof Error ? cause.message : String(cause),
        },
      },
      { status: 503 }
    )
  }

  const body = await response.arrayBuffer()
  const headers = new Headers()
  for (const name of ["content-type", "content-disposition"]) {
    const value = response.headers.get(name)
    if (value) headers.set(name, value)
  }
  // A download must never be served from a cache the UI does not control — and an export is a
  // one-shot record, so a cached copy would be a second file claiming to be the first.
  headers.set("Cache-Control", "no-store")

  return new Response(body, { status: response.status, headers })
}

/** Turn an `EngineProxyResult` into the route handler's response. */
export function proxyResponse(result: EngineProxyResult): Response {
  if (result.ok) {
    return Response.json(result.body, { status: result.status })
  }
  const { status, ...failure } = result.failure
  return Response.json(failure, { status })
}
