import path from "node:path";

import { createMDX } from "fumadocs-mdx/next";
import type { NextConfig } from "next";

const withMDX = createMDX();

const nextConfig: NextConfig = {
  // The shared UI package ships TypeScript sources, not a build artefact.
  transpilePackages: ["@workspace/ui"],

  /**
   * Same standalone output as apps/web and apps/marketing, and `outputFileTracingRoot` is
   * required for the same reason: `@workspace/ui` is consumed as source from outside this app,
   * so a trace rooted here silently omits it. Naming the monorepo root makes the trace include
   * it, at the cost of the standalone tree keeping the repo's shape — which is why a container
   * entrypoint would be `apps/docs/server.js` rather than `server.js`.
   */
  output: "standalone",
  outputFileTracingRoot: path.join(import.meta.dirname, "../.."),
};

export default withMDX(nextConfig);
