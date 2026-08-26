import path from "node:path"

import type { NextConfig } from "next"

const nextConfig: NextConfig = {
  transpilePackages: ["@workspace/ui"],

  /**
   * Emit a self-contained server bundle at `.next/standalone`, so the Docker image can run the app
   * without `node_modules` and without pnpm.
   *
   * `outputFileTracingRoot` is not optional here. In a pnpm workspace the app depends on
   * `@workspace/ui` and `@workspace/contracts`, which live *outside* `apps/web` and are consumed as
   * source rather than as built packages. Left to guess, Next traces from the app directory and
   * silently omits them; naming the monorepo root makes the trace include them, at the cost of the
   * standalone tree keeping the repo's own shape — which is why the container's entrypoint is
   * `apps/web/server.js` and not `server.js`.
   */
  output: "standalone",
  outputFileTracingRoot: path.join(import.meta.dirname, "../.."),

  /**
   * Kept out of the bundler and `require`d at run time instead.
   *
   * Both are the drivers Better Auth reaches the accounts database through (`lib/auth-db.ts`).
   * `better-sqlite3` is a native addon — a `.node` binary that cannot be bundled at all — and `pg`
   * resolves its own optional native accelerator at run time, which a bundler either inlines
   * incorrectly or warns about on every build. Naming them here also makes the standalone trace
   * copy them, so the container has the driver it needs.
   */
  serverExternalPackages: ["better-sqlite3", "pg"],
}

export default nextConfig
