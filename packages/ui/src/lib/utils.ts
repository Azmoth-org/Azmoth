import { clsx, type ClassValue } from "clsx"
import { extendTailwindMerge } from "tailwind-merge"

/**
 * `clsx` for the conditionals, `tailwind-merge` for the conflicts — and one extension, because
 * without it this function silently deletes the brand's display type.
 *
 * ## The bug this exists to prevent
 *
 * `tailwind-merge` resolves conflicts by parsing a class name into a group and keeping only the
 * last member of each group. It knows Tailwind's own scales; it cannot know a project's. `text-*`
 * is the ambiguous prefix — it is `font-size` for `text-lg` and `color` for `text-red-500` — and
 * the library disambiguates by looking the suffix up in the scales it was given. `display-xl` is in
 * none of them, so it was classified as a colour, and this happened:
 *
 *     cn("text-display-xl", "text-destructive")   // → "text-destructive"
 *
 * Two colours, last one wins, and the 48px is gone. Not an error, not a warning — a heading that
 * renders at the inherited 14px, which is exactly what it looks like when somebody forgot to write
 * a size at all. It cost an afternoon on the dashboard's metric tiles, where the figure is the
 * entire point of the component and it was rendering at body size.
 *
 * The four sizes come from `DESIGN.md` and are declared as `--text-display-*` in
 * `src/styles/globals.css`. Registering them here as what they are — font sizes — is what makes
 * `cn()` treat them as conflicting with `text-sm` (correct: both are sizes) rather than with
 * `text-destructive` (wrong: one is a size and one is a colour).
 *
 * Keep this list in step with the tokens. A size added to the stylesheet and not to this array is
 * not broken *yet* — it only breaks at the first call site that pairs it with a text colour, which
 * is a long way from the change that caused it.
 */
const twMerge = extendTailwindMerge({
  extend: {
    classGroups: {
      "font-size": [
        {
          text: ["display-xxl", "display-xl", "display-lg", "display-md"],
        },
      ],
    },
  },
})

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
