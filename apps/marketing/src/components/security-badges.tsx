import { useTranslations } from "next-intl";
import { DatabaseIcon, GlobeIcon, ScrollTextIcon, ServerIcon } from "lucide-react";

import { RevealGroup, RevealItem } from "@/components/reveal";

/**
 * Hosting and compliance as four checkable facts — including the ones that are not
 * finished yet.
 *
 * Every claim here is sourced from `legal/AVV_Anlage.md` and `legal/COMPLIANCE_ROADMAP.md`
 * rather than written for the page:
 *
 * - **AWS `eu-central-1`, Frankfurt am Main** — the region the AVV names for the
 *   application tier, marked as the *intended* region because the engine is not publicly
 *   deployed yet.
 * - **Neon, Frankfurt am Main** — the managed Postgres, on `aws-eu-central-1`, per the same
 *   annex, and reaching the public internet on the same schedule as the engine.
 * - **AVV & TOM** — both documents exist in `legal/`, both are drafts, and neither is a
 *   signed contract. The tile says so.
 * - **Vercel (EU)** — the one host that is actually serving something today: this site.
 *
 * ## What is deliberately not claimed
 *
 * These tiles used to be written in the present tense — "Anwendung: AWS", "Beide Dokumente
 * liegen vor und werden Vertragsbestandteil" — which described a deployment and a contract
 * that do not exist. The audience for this section is a Datenschutzbeauftragte doing
 * exactly one thing: checking whether the vendor's public claims survive a question. A
 * present-tense region for an engine that answers no requests is the claim that fails that
 * check fastest, and it fails it in the meeting where the deal is decided.
 *
 * The badges still say where the data will sit, not that the supply chain terminates in
 * Germany, because the AVV is explicit that it does not: Neon, LLC is a Databricks
 * subsidiary and leans on the Data Privacy Framework for transfers, and Vercel Inc. is a US
 * company. "Frankfurt-hosted" is true of the data at rest and is what the badge says.
 * "Deutsches Unternehmen, deutsche Server, keine US-Berührung" would be the version that
 * sells better and contradicts this company's own contract annex — and the reader most
 * likely to notice is precisely the compliance officer whose sign-off the deal needs.
 *
 * No ISO 27001, no BSI, no SOC 2, no TÜV mark either. A trust row is the easiest place on a
 * website to imply a certification through a logo without ever writing a sentence that is
 * false, and it is also the place where doing so is discovered fastest.
 *
 * ## Why word marks rather than vendor logos
 *
 * The brief asked for logo tiles. AWS, Neon and Vercel all restrict their marks to
 * customers following their brand guidelines, and using them next to a data-protection
 * claim edges toward implying an endorsement of that claim rather than merely naming the
 * host. Set in the site's own type beside a neutral icon, they read as infrastructure
 * disclosure, which is what they are.
 */

const BADGES = [
  { key: "aws", icon: ServerIcon },
  { key: "neon", icon: DatabaseIcon },
  { key: "dsgvo", icon: ScrollTextIcon },
  { key: "website", icon: GlobeIcon },
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
