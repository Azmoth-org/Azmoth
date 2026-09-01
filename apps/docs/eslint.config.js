import { nextJsConfig } from "@workspace/eslint-config/next-js"

/** @type {import("eslint").Linter.Config} */
export default [
  ...nextJsConfig,
  {
    /*
     * `.source/` is written by `fumadocs-mdx` on every install and build. It is generated,
     * `@ts-nocheck`'d by its own generator, and not committed — linting it reports on code
     * nobody can edit.
     */
    ignores: [".source/**"],
  },
]
