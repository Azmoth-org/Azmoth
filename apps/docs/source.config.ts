import { defineConfig, defineDocs } from "fumadocs-mdx/config";

/**
 * The content collection, and the whole of Fumadocs' build-time configuration.
 *
 * `fumadocs-mdx` reads this file — not `next.config.ts` — and writes a generated module to
 * `.source/`, which `lib/source.ts` then imports. That indirection is the reason MDX in this app
 * is typed: the frontmatter schema below is checked at build time and the generated module
 * carries the resulting types, so a page that forgets its `title` fails the build here rather
 * than rendering an empty `<h1>` in production.
 *
 * `dir` is the one thing worth stating explicitly. It is Fumadocs' own default, but the default
 * is invisible and this is the single sentence that says where the prose lives.
 */
export const docs = defineDocs({
  dir: "content/docs",
});

export default defineConfig({
  mdxOptions: {
    /*
     * Shiki, on one theme, because the site has one ground.
     *
     * A `light` key with no `dark` sibling, rather than the singular `theme` option — that one
     * does not survive Fumadocs' merge: its own `themes: { light: "github-light", dark:
     * "github-dark" }` default is spread underneath, so the highlighter preloads `min-light`
     * while shiki still takes the two-theme path and fails the build on a `github-light` it was
     * never asked to load. Naming the key Fumadocs already uses replaces the default instead of
     * sitting beside it.
     *
     * The dark half is dropped rather than set to something: `preset.css` reads `--shiki-dark`
     * only under a `.dark` selector, and this site never sets that class — so a second palette
     * would be two colour values per token in every code block, for a state that cannot occur.
     *
     * `min-light` rather than `github-light`: the preset overrides a code block's background to
     * `--fd-secondary` regardless, leaving only the token colours, and `min-light`'s are the
     * quieter set — which suits a page where the code is the evidence rather than the subject.
     */
    rehypeCodeOptions: {
      themes: { light: "min-light" },
    },
  },
});
