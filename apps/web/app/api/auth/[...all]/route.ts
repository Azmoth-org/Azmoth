/**
 * Every Better Auth endpoint: sign-up, sign-in, sign-out, session.
 *
 * A catch-all rather than a route per operation, because the set of endpoints is Better Auth's to
 * define — enabling a plugin adds paths under here, and a hand-written route per path would be a
 * list that silently falls behind the library.
 *
 * This is the one part of `/api/*` the middleware lets through unauthenticated, for the obvious
 * reason: signing in cannot require being signed in. It is also the only route group in this
 * application that talks to the database directly; everything under `/api/engine/*` proxies to the
 * FastAPI service instead.
 */

import { toNextJsHandler } from "better-auth/next-js"

import { getAuth } from "@/lib/auth"

/**
 * The handler is resolved per request, not at import time.
 *
 * `getAuth()` opens the accounts database on first use, and `next build` imports every route to
 * collect its page data — so building the instance at module scope would make a container image
 * impossible to build without the deployment's database credentials in hand. See `lib/auth.ts`.
 */
export const { GET, POST } = toNextJsHandler((request: Request) =>
  getAuth().handler(request)
)
