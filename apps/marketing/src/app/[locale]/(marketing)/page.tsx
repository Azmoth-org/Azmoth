import type { Metadata } from "next";
import { useTranslations } from "next-intl";
import { getTranslations, setRequestLocale } from "next-intl/server";
import {
  ArrowRightIcon,
  CalendarClockIcon,
  FileCheckIcon,
  GitCompareArrowsIcon,
  LayersIcon,
  ScaleIcon,
  ScrollTextIcon,
} from "lucide-react";

import { Badge } from "@workspace/ui/components/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@workspace/ui/components/card";

import { ButtonLink } from "@/components/button-link";
import { Section, SectionHeading } from "@/components/section";
import { buildPageMetadata } from "@/lib/seo";
import { getProductLinks, routes, siteConfig } from "@/lib/site";

/** Same order as `startseite.funktionen.punkte` — the copy lives in the catalogue. */
const FEATURE_ICONS = [
  GitCompareArrowsIcon,
  ScrollTextIcon,
  ScaleIcon,
  CalendarClockIcon,
  LayersIcon,
  FileCheckIcon,
] as const;

type Step = { titel: string; text: string };
type Feature = { titel: string; text: string };

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "metadaten" });

  return buildPageMetadata({
    path: "/",
    // `absolute`, so the root template does not turn this into
    // "Azmoth – Deterministische GOÄ-Prüfengine · Azmoth".
    title: { absolute: siteConfig.title },
    description: t("startseiteBeschreibung"),
    keywords: ["GOÄ", "Privatliquidation", "Rechnungsprüfung", "PADnext", "Abrechnung"],
  });
}

export default async function HomePage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);

  return (
    <>
      <Hero />
      <Workflow />
      <Features />
      <Limits />
      <ClosingCta />
    </>
  );
}

function Hero() {
  const t = useTranslations("startseite.hero");

  return (
    <Section className="pt-16 pb-20 lg:pt-24 lg:pb-28">
      <div className="mx-auto flex max-w-3xl flex-col items-center gap-6 text-center">
        <Badge variant="secondary">{t("badge")}</Badge>
        <h1 className="font-heading text-balance text-4xl font-semibold tracking-tight sm:text-5xl lg:text-6xl">
          {t("titel")}
        </h1>
        <p className="max-w-2xl text-pretty text-base text-muted-foreground sm:text-lg">
          {t("untertitel")}
        </p>
        {/*
          The two tracks, in the order a stranger can use them. Primary is the demo, which needs no
          account and takes no upload; secondary is the gated pilot. Before `SIGNUP_ALLOWLIST` the
          primary button pointed at `signup`, which now refuses anyone not on the list — a button
          labelled "kostenlos testen" that leads to a refusal is worse than no button.
        */}
        <div className="mt-2 flex flex-col gap-3 sm:flex-row">
          <ButtonLink external href={getProductLinks().demo} size="lg">
            {t("ctaPrimaer")}
            <ArrowRightIcon data-icon="inline-end" />
          </ButtonLink>
          <ButtonLink
            external
            href={getProductLinks().signup}
            size="lg"
            variant="outline"
          >
            {t("ctaSekundaer")}
          </ButtonLink>
        </div>
        <p className="text-xs text-muted-foreground">{t("hinweis")}</p>
      </div>
    </Section>
  );
}

function Workflow() {
  const t = useTranslations("startseite.ablauf");
  const steps = t.raw("schritte") as Step[];

  return (
    <Section className="border-t border-border/60">
      <SectionHeading title={t("titel")} subtitle={t("untertitel")} />
      <ol className="mt-14 grid gap-6 md:grid-cols-3">
        {steps.map((step, index) => (
          <li key={step.titel}>
            <Card className="h-full">
              <CardHeader>
                <span
                  aria-hidden="true"
                  className="mb-2 flex size-9 items-center justify-center rounded-full bg-primary/10 font-heading text-sm font-semibold text-primary"
                >
                  {index + 1}
                </span>
                <CardTitle>{step.titel}</CardTitle>
              </CardHeader>
              <CardContent className="text-muted-foreground">{step.text}</CardContent>
            </Card>
          </li>
        ))}
      </ol>
    </Section>
  );
}

function Features() {
  const t = useTranslations("startseite.funktionen");
  const features = t.raw("punkte") as Feature[];

  return (
    <Section className="border-t border-border/60">
      <SectionHeading title={t("titel")} subtitle={t("untertitel")} />
      <ul className="mt-14 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
        {features.map((feature, index) => {
          const Icon = FEATURE_ICONS[index] ?? FileCheckIcon;
          return (
            <li key={feature.titel}>
              <Card className="h-full">
                <CardHeader>
                  <Icon aria-hidden="true" className="mb-2 size-5 text-primary" />
                  <CardTitle>{feature.titel}</CardTitle>
                </CardHeader>
                <CardContent className="text-muted-foreground">
                  {feature.text}
                </CardContent>
              </Card>
            </li>
          );
        })}
      </ul>
    </Section>
  );
}

function Limits() {
  const t = useTranslations("startseite.grenzen");
  const points = t.raw("punkte") as string[];

  return (
    <Section className="border-t border-border/60">
      <SectionHeading title={t("titel")} subtitle={t("untertitel")} align="start" />
      <ul className="mt-10 flex max-w-3xl flex-col gap-4">
        {points.map((point) => (
          <li
            key={point}
            className="border-l-2 border-border py-1 pl-4 text-muted-foreground"
          >
            {point}
          </li>
        ))}
      </ul>
    </Section>
  );
}

function ClosingCta() {
  const t = useTranslations("startseite.cta");

  return (
    <Section className="border-t border-border/60">
      <div className="rounded-4xl bg-card px-6 py-14 text-center ring-1 ring-foreground/5 sm:px-12">
        <SectionHeading title={t("titel")} subtitle={t("text")} />
        <div className="mt-8 flex flex-col justify-center gap-3 sm:flex-row">
          <ButtonLink external href={getProductLinks().signup} size="lg">
            {t("primaer")}
            <ArrowRightIcon data-icon="inline-end" />
          </ButtonLink>
          <ButtonLink href={routes.kontakt} size="lg" variant="outline">
            {t("sekundaer")}
          </ButtonLink>
        </div>
      </div>
    </Section>
  );
}
