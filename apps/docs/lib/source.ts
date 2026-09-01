import { loader } from "fumadocs-core/source";
import { icons } from "lucide-react";
import { createElement } from "react";

import { docs } from "@/.source/server";

/**
 * The content tree, loaded once.
 *
 * `baseUrl: "/"` and not `"/docs"`. This application *is* `docs.azmoth.com` — a subdomain, not
 * a section of the marketing site — so a `/docs` prefix would put the landing page at
 * `docs.azmoth.com/docs`, which reads as a mistake and costs a redirect on the one URL the
 * footer and the header both point at. The trade is that the content directory's name no longer
 * appears in the URL, which is why `source.config.ts` says where it is.
 *
 * `icon` resolves the `icon:` frontmatter key against lucide's exported set, which is what lets
 * a page choose its sidebar icon in MDX rather than in a lookup table maintained here. An
 * unknown name is `undefined` rather than a build failure: a missing icon is a page without a
 * glyph, and failing the whole site over one is a worse trade than the alternative.
 */
export const source = loader({
  source: docs.toFumadocsSource(),
  baseUrl: "/",
  icon(icon) {
    if (!icon) return;
    if (icon in icons) {
      return createElement(icons[icon as keyof typeof icons], {
        // The sidebar sets its own size; `absolute` stroke keeps a 16px glyph from thinning out.
        "aria-hidden": "true",
      });
    }
  },
});
