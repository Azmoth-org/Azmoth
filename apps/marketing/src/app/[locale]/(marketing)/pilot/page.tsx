import type { Metadata } from "next";
import { useTranslations } from "next-intl";
import { getTranslations, setRequestLocale } from "next-intl/server";
import {
  ArrowRightIcon,
  CalendarIcon,
  CheckIcon,
  ClipboardListIcon,
  HandshakeIcon,
  LockIcon,
  ScaleIcon,
  SigmaIcon,
} from "lucide-react";

import { Card, CardContent, CardHeader } from "@workspace/ui/components/card";

import { ButtonLink } from "@/components/button-link";
import { CardHeading } from "@/components/card-heading";
import { GradientMesh } from "@/components/gradient-mesh";
import { Metrics } from "@/components/metrics";
import { PipelineFlow } from "@/components/pipeline-flow";
import { Reveal, RevealGroup, RevealItem } from "@/components/reveal";
import { Section, SectionHeading } from "@/components/section";
import { SecurityBadges } from "@/components/security-badges";
import { TrustBadges } from "@/components/trust-badges";
import { buildPageMetadata } from "@/lib/seo";
import { getProductLinks, routes, siteConfig } from "@/lib/site";

/**
 * The dedicated pilot landing page — where every "Pilot-Zugang anfordern" link on the rest of
 * the site could reasonably send someone who wants the whole pitch in one place rather than the
 * one-paragraph version embedded in the homepage or the one-line ask on `/kontakt`.
 *
 * Nothing here claims more than `startseite.pilot`, `legal/PILOT_VEREINBARUNG.md` and
 * `components/metrics.tsx` already commit to elsewhere on this site: synthetic data only,
 * six to eight weeks, free, allowlist-gated. This page exists to say it once, fully, with the
 * evidence beside it — not to add a new promise.
 */

const VERIFIZIERBARKEIT_ICONS = [LockIcon, SigmaIcon, ScaleIcon] as const;

type Punkt = { titel: string; text: string };

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "metadaten" });

  return buildPageMetadata({
    path: "/pilot",
    title: t("pilotTitel"),
    description: t("pilotBeschreibung"),
  });
}

export default async function PilotPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);

  return (
    <>
      <PilotHero />
      <PilotUmfang />
      <PilotAbdeckung />
      <PilotArchitektur />
      <PilotVerifizierbarkeit />
      <PilotCta />
    </>
  );
}

/* --- 1. Hero -------------------------------------------------------------------- */

function PilotHero() {
  const t = useTranslations("pilot.hero");
  const links = getProductLinks();

  return (
    <Section className="pt-16 pb-20 lg:pt-24 lg:pb-28" backdrop={<GradientMesh />}>
      <div className="mx-auto flex max-w-3xl flex-col items-center gap-6 text-center">
        <SectionHeading
          eyebrow={t("eyebrow")}
          title={t("titel")}
          subtitle={t("untertitel")}
          as="h1"
        />
        <Reveal delay={0.1}>
          <ButtonLink external href={links.signup} size="lg">
            {t("ctaPrimaer")}
            <CalendarIcon data-icon="inline-end" />
          </ButtonLink>
        </Reveal>
        <Reveal delay={0.15}>
          <p className="max-w-xl text-xs leading-relaxed text-muted-foreground">
            {t("hinweis")}
          </p>
        </Reveal>
        <Reveal delay={0.2} className="mt-2">
          <TrustBadges />
        </Reveal>
      </div>
    </Section>
  );
}

/* --- 2. What you get, what we ask ------------------------------------------------ */

function PilotUmfang() {
  const t = useTranslations("pilot.umfang");
  const bekommt = t.raw("bekommt") as string[];
  const bitten = t.raw("bitten") as string[];

  return (
    <Section tone="soft" className="border-y border-azm-hairline">
      <SectionHeading
        eyebrow={t("eyebrow")}
        title={t("titel")}
        subtitle={t("untertitel")}
      />
      <RevealGroup as="ul" className="mt-14 grid gap-6 md:grid-cols-2">
        <RevealItem>
          <Card className="h-full bg-white ring-1 ring-azm-hairline">
            <CardHeader>
              <span className="mb-3 flex size-10 items-center justify-center rounded-xl bg-primary/10 text-primary">
                <HandshakeIcon aria-hidden="true" className="size-5" />
              </span>
              <CardHeading>{t("bekommtTitel")}</CardHeading>
            </CardHeader>
            <CardContent>
              <ul className="flex flex-col gap-3">
                {bekommt.map((point) => (
                  <li key={point} className="flex gap-3 text-muted-foreground">
                    <CheckIcon
                      aria-hidden="true"
                      className="mt-0.5 size-4 shrink-0 text-primary"
                    />
                    <span>{point}</span>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        </RevealItem>
        <RevealItem>
          <Card className="h-full bg-white ring-1 ring-azm-hairline">
            <CardHeader>
              <span className="mb-3 flex size-10 items-center justify-center rounded-xl bg-primary/10 text-primary">
                <ClipboardListIcon aria-hidden="true" className="size-5" />
              </span>
              <CardHeading>{t("bittenTitel")}</CardHeading>
            </CardHeader>
            <CardContent>
              <ul className="flex flex-col gap-3">
                {bitten.map((point) => (
                  <li key={point} className="flex gap-3 text-muted-foreground">
                    <CheckIcon
                      aria-hidden="true"
                      className="mt-0.5 size-4 shrink-0 text-primary"
                    />
                    <span>{point}</span>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        </RevealItem>
      </RevealGroup>
    </Section>
  );
}

/* --- 3. The honest coverage number ------------------------------------------------ */

/**
 * The exact heading and tiles the homepage uses for this — `startseite.zahlen` plus `<Metrics>`.
 * Reused rather than restated: the point of this section is that the number is pinned by the
 * engine's own test suite, and copying its wording onto a second page would be the same claim
 * typed twice, which is exactly the drift `lib/engine-facts.ts` exists to prevent.
 */
function PilotAbdeckung() {
  const t = useTranslations("startseite.zahlen");

  return (
    <Section>
      <SectionHeading
        eyebrow={t("eyebrow")}
        title={t("titel")}
        subtitle={t("untertitel")}
      />
      <Metrics />
    </Section>
  );
}

/* --- 4. Architecture -------------------------------------------------------------- */

function PilotArchitektur() {
  const t = useTranslations("pilot.architektur");

  return (
    <Section tone="soft" className="border-y border-azm-hairline">
      <SectionHeading
        eyebrow={t("eyebrow")}
        title={t("titel")}
        subtitle={t("untertitel")}
      />
      <div className="mx-auto mt-14 max-w-4xl">
        <PipelineFlow />
      </div>
    </Section>
  );
}

/* --- 5. Verifiable instead of certified ------------------------------------------- */

/**
 * What a Datenschutzbeauftragte or IT evaluator gets in place of a vendor certification.
 *
 * There is no ISO 27001, SOC 2 or TÜV mark to show for a six-week pilot — `components/
 * security-badges.tsx` already declines to imply one with a logo, and this section declines to
 * imply one with the word "Sicherheitsaudit" either. What it states instead are three properties
 * enforced in the application itself: the synthetic-data rule, the receipt hash's determinism,
 * and the three-bucket verdict model — each one a claim a technical evaluator can check against
 * the demo rather than one they have to take on trust.
 */
function PilotVerifizierbarkeit() {
  const t = useTranslations("pilot.verifizierbarkeit");
  const punkte = t.raw("punkte") as Punkt[];
  const tSicherheit = useTranslations("startseite.sicherheit");

  return (
    <Section>
      <SectionHeading
        eyebrow={t("eyebrow")}
        title={t("titel")}
        subtitle={t("untertitel")}
      />
      <RevealGroup as="ul" className="mt-14 grid gap-4 sm:gap-6 md:grid-cols-3">
        {punkte.map((punkt, index) => {
          const Icon = VERIFIZIERBARKEIT_ICONS[index] ?? ScaleIcon;
          return (
            <RevealItem key={punkt.titel}>
              <div className="azm-lift flex h-full flex-col gap-3 rounded-2xl bg-white p-6 ring-1 ring-azm-hairline">
                <span className="flex size-10 items-center justify-center rounded-xl bg-primary/10 text-primary">
                  <Icon aria-hidden="true" className="size-5" />
                </span>
                <p className="font-medium text-azm-ink">{punkt.titel}</p>
                <p className="leading-relaxed text-muted-foreground">{punkt.text}</p>
              </div>
            </RevealItem>
          );
        })}
      </RevealGroup>

      <Reveal delay={0.1} className="mt-14">
        <p className="mx-auto max-w-2xl text-center text-sm font-medium text-azm-ink-mute">
          {tSicherheit("titel")}
        </p>
      </Reveal>
      <div className="mt-6">
        <SecurityBadges />
      </div>
    </Section>
  );
}

/* --- 6. Closing CTA ---------------------------------------------------------------- */

function PilotCta() {
  const t = useTranslations("pilot.cta");
  const links = getProductLinks();

  return (
    <Section tone="cream" className="border-t border-azm-hairline">
      <div className="mx-auto flex max-w-2xl flex-col items-center gap-6 text-center">
        <SectionHeading title={t("titel")} subtitle={t("text")} />
        <Reveal delay={0.1} className="flex w-full flex-col justify-center gap-3 sm:w-auto sm:flex-row">
          <ButtonLink external href={links.signup} size="lg">
            {t("primaer")}
            <ArrowRightIcon data-icon="inline-end" />
          </ButtonLink>
          <ButtonLink href={routes.kontakt} size="lg" variant="outline">
            {t("sekundaer")}
          </ButtonLink>
        </Reveal>
        <p className="text-xs text-muted-foreground">{siteConfig.email}</p>
      </div>
    </Section>
  );
}
