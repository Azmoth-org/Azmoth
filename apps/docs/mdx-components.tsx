import defaultMdxComponents from "fumadocs-ui/mdx";
import { Step, Steps } from "fumadocs-ui/components/steps";
import { Tab, Tabs } from "fumadocs-ui/components/tabs";
import type { MDXComponents } from "mdx/types";

/**
 * The component vocabulary every MDX page can reach without importing anything.
 *
 * Fumadocs' defaults cover the prose elements plus `Card`, `Cards` and `Callout`. The three
 * added here are the ones this site's content actually uses — `Steps` for an ordered procedure
 * where each step carries a paragraph, and `Tabs` for the same call in two languages. Anything
 * beyond that is an import in the page that needs it: a component registered here is in the
 * bundle of every page, whether or not it renders.
 */
export function getMDXComponents(components?: MDXComponents): MDXComponents {
  return {
    ...defaultMdxComponents,
    Step,
    Steps,
    Tab,
    Tabs,
    ...components,
  };
}
