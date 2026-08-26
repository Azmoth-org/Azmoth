/**
 * Better Auth from the browser. The counterpart to `lib/auth.ts`, which must never be imported here.
 *
 * No `baseURL`: every call is same-origin, to the `/api/auth/*` handler this application serves
 * itself. Naming an origin would only be needed if the auth server lived somewhere else, and
 * hard-coding one is how a preview deployment ends up posting its credentials to production.
 */

import { createAuthClient } from "better-auth/react"

export const authClient = createAuthClient()

export const { signIn, signOut, signUp, useSession } = authClient
