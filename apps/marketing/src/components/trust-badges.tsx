import { useTranslations } from "next-intl";
import { CheckIcon, LockIcon, ShieldCheckIcon, SigmaIcon } from "lucide-react";

import { cn } from "@workspace/ui/lib/utils";

/**
 * The four claims under the hero call-to-action.
 *
 * Each one is a statement a visitor could check, which is the only kind worth putting
 * here: hosting region, the pilot's data rule, and the absence of a language model are
 * all facts about how this is built rather than adjectives about how good it is.
 *
 * The German flag is a text glyph rather than an icon or an image. An SVG tricolour is
 * three more elements to style at 16px, and an emoji flag is the one case where the
 * platform font is more reliable than anything shipped — with the caveat that Windows
 * renders 🇩🇪 as the letters "DE", which is why the label reads "Made in Germany"
 * beside it rather than depending on the glyph to carry the meaning.
 */
const BADGES = [
  { key: "madeInGermany", icon: null, flag: "🇩🇪" },
  { key: "dsgvo", icon: ShieldCheckIcon, flag: null },
  { key: "keinePatientendaten", icon: LockIcon, flag: null },
  { key: "deterministisch", icon: SigmaIcon, flag: null },
] as const;

export function TrustBadges({ className }: { className?: string }) {
  const t = useTranslations("vertrauen");

  return (
    <ul className={cn("flex flex-wrap justify-center gap-2 sm:gap-3", className)}>
      {BADGES.map(({ key, icon: Icon, flag }) => (
        <li
          key={key}
          className="flex items-center gap-2 rounded-full border border-azm-hairline bg-white/80 px-3 py-1.5 text-xs font-medium text-azm-ink-secondary shadow-[0_1px_3px_rgba(0,55,112,0.06)] backdrop-blur-sm"
        >
          {flag ? (
            <span aria-hidden="true" className="text-sm leading-none">
              {flag}
            </span>
          ) : Icon ? (
            <Icon aria-hidden="true" className="size-3.5 text-primary" />
          ) : (
            <CheckIcon aria-hidden="true" className="size-3.5 text-primary" />
          )}
          {t(key)}
        </li>
      ))}
    </ul>
  );
}
