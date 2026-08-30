/**
 * `GET|POST /api/engine/settings/api-keys`
 *   → `GET|POST {ENGINE_BASE_URL}/api/v1/settings/api-keys`
 *
 * The practice's API keys: list them, or mint one.
 *
 * **`POST` is the only response in this application that carries a secret**, and it carries it
 * exactly once — the engine stores a SHA-256 hash, so nothing can produce the token again. The
 * response is passed through untouched and is not logged here, because a proxy that helpfully
 * echoed a response body into a server log would put a live credential in it.
 *
 * Both verbs go through `callEngine`, which resolves the session and forwards the organisation. A
 * caller therefore cannot mint a key for a practice they are not signed in to: there is no field in
 * which to name one.
 */

import { callEngine, proxyResponse } from "@/lib/engine"

export async function GET(): Promise<Response> {
  return proxyResponse(await callEngine("/api/v1/settings/api-keys"))
}

export async function POST(request: Request): Promise<Response> {
  // A missing or unparsable body is treated as an empty one rather than refused: the only field is
  // an optional label, and failing a mint because the client sent no JSON would be a worse
  // experience than minting an unlabelled key.
  let body: unknown = {}
  try {
    body = await request.json()
  } catch {
    body = {}
  }

  return proxyResponse(
    await callEngine("/api/v1/settings/api-keys", { method: "POST", body })
  )
}
