import { createFromSource } from "fumadocs-core/search/server";

import { source } from "@/lib/source";

/**
 * The search index, served from the same content tree the pages render from.
 *
 * A route handler rather than an index file shipped to the browser: the two cannot disagree
 * about what exists, and the corpus stays on the server rather than being downloaded by every
 * visitor whether or not they ever open the search dialog.
 *
 * The index is built once per server instance from `source` — the same loader the pages use —
 * so a page that renders is a page that is searchable, with nothing to keep in step.
 */
export const { GET } = createFromSource(source);
