/**
 * `POST /api/demo/audit` → `POST {ENGINE_BASE_URL}/api/v1/demo/audit`
 *
 * **Public.** `middleware.ts` names `/api/demo` in `PUBLIC_PREFIXES`, so this is reachable without
 * a session — the only proxy route in the application that is.
 *
 * What makes that safe is not this file, it is the endpoint behind it: the engine's demo route
 * takes no body, no query and no path parameter, and audits one committed synthetic delivery whose
 * path is a constant. So there is no request a visitor can compose that causes anything of theirs
 * to be processed. See `apps/engine/app/api/demo.py`, and `apps/engine/tests/test_demo.py` for the
 * tests that fail if that ever stops being true.
 *
 * The request body is deliberately **not read and not forwarded**. A visitor who POSTs a file here
 * gets the synthetic report, exactly as if they had sent nothing — which is the behaviour that
 * keeps this from being an upload form by accident.
 */

import { callPublicEngine, proxyResponse } from "@/lib/engine"

export async function POST(): Promise<Response> {
  return proxyResponse(await callPublicEngine("/api/v1/demo/audit"))
}
