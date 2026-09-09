import { useTranslations } from "next-intl";
import { LockIcon, ShieldCheckIcon, SigmaIcon } from "lucide-react";

import { cn } from "@workspace/ui/lib/utils";

/**
 * The three claims under the hero call-to-action.
 *
 * Each one is a statement a visitor could check, which is the only kind worth putting
 * here: the pilot's data rule, the scope of the data-protection claim, and the absence of
 * a language model are all facts about how this is built rather than adjectives about how
 * good it is.
 *
 * A fourth badge used to sit first in this row: a 🇩🇪 glyph reading "Made in Germany". It
 * is gone because it was not true — Azmoth is operated from Tunisia, this site is served
 * by Vercel, and the Impressum now says both. It was also the single most load-bearing
 * claim on the page for the audience that matters, since a German billing centre reads a
 * flag next to "DSGVO-konform" as a statement about jurisdiction. Getting caught on it
 * costs more than the badge was ever worth.
 *
 * `dsgvo` is qualified for the same reason. Unqualified, it claims a compliance posture
 * for processing that has not been contracted yet; qualified to synthetic test data, it
 * claims exactly what `legal/AVV_Anlage.md` and the Datenschutzerklärung already say.
 */
const BADGES = [
  { key: "dsgvo", icon: ShieldCheckIcon },
  { key: "keinePatientendaten", icon: LockIcon },
  { key: "deterministisch", icon: SigmaIcon },
] as const;

export function TrustBadges({ className }: { className?: string }) {
  const t = useTranslations("vertrauen");

  return (
    <ul className={cn("flex flex-wrap justify-center gap-2 sm:gap-3", className)}>
      {BADGES.map(({ key, icon: Icon }) => (
        <li
          key={key}
          className="flex items-center gap-2 rounded-full border border-azm-hairline bg-white/80 px-3 py-1.5 text-xs font-medium text-azm-ink-secondary shadow-[0_1px_3px_rgba(0,55,112,0.06)] backdrop-blur-sm"
        >
          <Icon aria-hidden="true" className="size-3.5 shrink-0 text-primary" />
          {t(key)}
        </li>
      ))}
    </ul>
  );
}
