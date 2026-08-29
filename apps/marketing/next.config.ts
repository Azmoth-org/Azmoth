import path from "node:path";

import createNextIntlPlugin from "next-intl/plugin";
import type { NextConfig } from "next";

/**
 * The plugin is what makes `useTranslations` work at build time: it points the
 * request config at `src/i18n/request.ts`, without which every statically
 * generated page fails with "Couldn't find next-intl config file".
 */
const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");

const nextConfig: NextConfig = {
  // The shared UI package ships TypeScript sources, not a build artefact.
  transpilePackages: ["@workspace/ui"],

  /**
   * Emit a self-contained server bundle at `.next/standalone`, so the production
   * image can run without `node_modules` and without pnpm. Same reasoning as
   * apps/web, and `outputFileTracingRoot` is required for the same reason: in a
   * pnpm workspace `@workspace/ui` lives outside this app and is consumed as
   * source, so a trace rooted at the app directory silently omits it. Naming the
   * monorepo root makes the trace include it, at the cost of the standalone tree
   * keeping the repo's shape — which is why the container's entrypoint is
   * `apps/marketing/server.js` and not `server.js`.
   */
  output: "standalone",
  outputFileTracingRoot: path.join(import.meta.dirname, "../.."),
};

export default withNextIntl(nextConfig);
