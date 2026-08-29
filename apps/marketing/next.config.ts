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
};

export default withNextIntl(nextConfig);
