/**
 * The browser half of Better Auth. **Client-only — the counterpart to `lib/auth.ts`.**
 *
 * No `baseURL`. The client defaults to the origin the page was served from, which is the only origin
 * this application's auth endpoints are ever reached on — and stating one here would break exactly
 * the deployments `trustedOrigins` in `lib/auth.ts` exists to support, where the container's idea of
 * its own address is not the browser's.
 *
 * `organizationClient` mirrors the server's `organization()` plugin. Registering it is what turns the
 * plugin's endpoints into `authClient.organization.*` calls and its atoms into hooks — Better Auth's
 * React client exposes an atom named `x` as `useX`, so the plugin's `listOrganizations` and
 * `activeOrganization` arrive as `useListOrganizations()` and `useActiveOrganization()`. The two
 * halves have to agree: a client plugin without its server counterpart calls endpoints that answer
 * 404, and a server plugin without its client counterpart leaves `authClient.organization` undefined.
 */

import { organizationClient } from "better-auth/client/plugins"
import { createAuthClient } from "better-auth/react"

export const authClient = createAuthClient({
  plugins: [organizationClient()],
})

export const { signIn, signOut, signUp, useSession } = authClient

/**
 * The organisation hooks, re-exported so components import a name rather than reach through the
 * client object. `useListOrganizations` is every organisation the signed-in user is a member of;
 * `useActiveOrganization` is the one their session is currently scoped to, and it is `null` for an
 * account that belongs to none.
 */
export const { useListOrganizations, useActiveOrganization } = authClient
