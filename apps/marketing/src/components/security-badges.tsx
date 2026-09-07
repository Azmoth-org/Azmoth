import { useTranslations } from "next-intl";
import { DatabaseIcon, LockIcon, ScrollTextIcon, ServerIcon } from "lucide-react";

import { RevealGroup, RevealItem } from "@/components/reveal";

/**
 * Hosting and compliance as four checkable facts.
 *
 * Every claim here is sourced from `legal/AVV_Anlage.md` rather than written for the page:
 *
 * - **AWS `eu-central-1`, Frankfurt am Main** — the AVV names the region for the application tier.
 * - **Neon, Frankfurt am Main** — the managed Postgres, on `aws-eu-central-1`, per the same annex.
 * - **AVV & TOM** — both documents exist in `legal/` and are the ones a Datenschutzbeauftragte
 *   asks for; this is not a claim about a certification nobody holds.
 * - **No patient data in the pilot** — the constraint the pilot programme already states, and the
 *   only one of the four that is a *promise* rather than an infrastructure fact.
 *
 * ## What is deliberately not claimed
 *
 * The badges say where the data sits, not that the supply chain terminates in Germany, because the
 * AVV is explicit that it does not: Neon, LLC is a Databricks subsidiary and leans on the Data
 * Privacy Framework for transfers. "Frankfurt-hosted" is true and is what the badge says.
 * "Deutsches Unternehmen, deutsche Server, keine US-Berührung" would be the version that sells
 * better and contradicts this company's own contract annex — and the reader most likely to notice
 * is precisely the compliance officer whose sign-off the deal needs.
 *
 * No ISO 27001, no BSI, no SOC 2, no TÜV mark either. A trust row is the easiest place on a
 * website to imply a certification through a logo without ever writing a sentence that is false,
 * and it is also the place where doing so is discovered fastest.
 *
 * ## Why word marks rather than vendor logos
 *
 * The brief asked for logo tiles. AWS and Neon both restrict their marks to customers following
 * their brand guidelines, and using them next to "DSGVO-konform" edges toward implying an
 * endorsement of the compliance claim rather than merely naming the host. Set in the site's own
 * type beside a neutral icon, they read as infrastructure disclosure, which is what they are.
 */

const BADGES = [
  { key: "aws", icon: ServerIcon },
  { key: "neon", icon: DatabaseIcon },
  { key: "dsgvo", icon: ScrollTextIcon },
  { key: "pilot", icon: LockIcon },
] as const;

export function SecurityBadges() {
  const t = useTranslations("startseite.sicherheit");

  return (
    <RevealGroup as="ul" className="mt-14 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {BADGES.map(({ key, icon: Icon }) => (
        <RevealItem key={key}>
          <div className="azm-lift flex h-full flex-col gap-3 rounded-2xl bg-white p-6 ring-1 ring-azm-hairline">
            <span className="flex size-10 items-center justify-center rounded-xl bg-primary/10 text-primary">
              <Icon aria-hidden="true" className="size-5" />
            </span>
            <p className="font-medium text-azm-ink">{t(`${key}.titel`)}</p>
            {/*
              The second line carries a region string or a document name, so `azm-tnum` keeps
              `eu-central-1` from setting with proportional digits beside the three tiles that have
              none.
            */}
            <p className="azm-tnum text-sm leading-relaxed text-muted-foreground">
              {t(`${key}.text`)}
            </p>
          </div>
        </RevealItem>
      ))}
    </RevealGroup>
  );
}
