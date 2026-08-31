import type { Metadata } from "next";
import { useTranslations } from "next-intl";
import { getTranslations, setRequestLocale } from "next-intl/server";
import {
  ArrowRightIcon,
  BuildingIcon,
  CheckIcon,
  CircleAlertIcon,
  CircleCheckIcon,
  CircleHelpIcon,
  ClockIcon,
  CpuIcon,
  EyeOffIcon,
  FileCheckIcon,
  GaugeIcon,
  PlugIcon,
  ScaleIcon,
  ShieldCheckIcon,
  StethoscopeIcon,
  TerminalIcon,
  TriangleAlertIcon,
  UploadIcon,
} from "lucide-react";

import { Badge } from "@workspace/ui/components/badge";
import {Card, CardContent, CardHeader} from "@workspace/ui/components/card";

import { ButtonLink } from "@/components/button-link";
import { CardHeading } from "@/components/card-heading";
import { CodeBlock } from "@/components/code-block";
import { GradientMesh } from "@/components/gradient-mesh";
import { Section, SectionHeading } from "@/components/section";
import { TrustBadges } from "@/components/trust-badges";
import { CURL_EXAMPLE } from "@/lib/api-example";
import { engineFacts } from "@/lib/engine-facts";
import { buildPageMetadata } from "@/lib/seo";
import { apiDocsUrl, getProductLinks, routes, siteConfig } from "@/lib/site";

/*
 * Icons live beside the copy they illustrate only by index — the strings themselves are
 * in `messages/de.json`, because a marketing page is edited by whoever writes the copy
 * and they should not have to open a `.tsx` to change a sentence. Each array below is in
 * the same order as its catalogue key, and the fallbacks make a length mismatch render
 * plainly rather than crash the build.
 */
const PROBLEM_ICONS = [ClockIcon, TriangleAlertIcon, EyeOffIcon] as const;
const STEP_ICONS = [UploadIcon, CpuIcon, FileCheckIcon] as const;
const FEATURE_ICONS = [
  CpuIcon,
  ScaleIcon,
  GaugeIcon,
  FileCheckIcon,
  PlugIcon,
  ShieldCheckIcon,
] as const;
const AUDIENCE_ICONS = [BuildingIcon, TerminalIcon, StethoscopeIcon] as const;

/**
 * The three verdict buckets, keyed to the tokens in globals.css.
 *
 * The colours are not decoration and are not chosen here: they are the same green, red
 * and amber the engine's own report renders, so a visitor who reads this section and
 * then opens the demo sees one product rather than two. See `--azm-confirmed` and its
 * neighbours for why that is enforced in the token layer rather than by convention.
 */
const BUCKETS = [
  {
    icon: CircleCheckIcon,
    ring: "ring-azm-confirmed/25",
    surface: "bg-azm-confirmed-bg",
    accent: "text-azm-confirmed",
    bar: "bg-azm-confirmed",
  },
  {
    icon: CircleAlertIcon,
    ring: "ring-azm-wrong/25",
    surface: "bg-azm-wrong-bg",
    accent: "text-azm-wrong",
    bar: "bg-azm-wrong",
  },
  {
    icon: CircleHelpIcon,
    ring: "ring-azm-unconfirmed/30",
    surface: "bg-azm-unconfirmed-bg",
    accent: "text-azm-unconfirmed",
    bar: "bg-azm-unconfirmed",
  },
] as const;

type Titled = { titel: string; text: string };
type Audience = Titled & { cta: string };

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
    keywords: [
      "GOÄ",
      "GOÄ-Prüfung",
      "Abrechnungsstelle",
      "PVS",
      "Privatliquidation",
      "Rechnungsprüfung",
      "PADnext",
      "Abrechnung",
    ],
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
      <Problem />
      <Workflow />
      <Buckets />
      <Features />
      <Audiences />
      <Pilot />
      <ApiTeaser />
      <ClosingCta />
    </>
  );
}

/* --- 1. Hero ------------------------------------------------------------------ */

function Hero() {
  const t = useTranslations("startseite.hero");
  const links = getProductLinks();

  return (
    <Section
      className="pt-14 pb-20 lg:pt-20 lg:pb-28"
      backdrop={<GradientMesh />}
      aria-labelledby="hero-titel"
    >
      <div className="mx-auto flex max-w-4xl flex-col items-center gap-6 text-center">
        {/*
          `whitespace-normal` and `h-auto` undo two of Badge's defaults on purpose. The
          shared component is built for a one-word status chip, so it is a fixed-height
          `whitespace-nowrap` pill; this eyebrow is a sixty-character German noun phrase
          and at 390px it was 424px wide, which is the whole of the mobile page's
          horizontal overflow. It wraps to two lines instead.
        */}
        <Badge
          variant="secondary"
          className="h-auto max-w-full px-3 py-1 text-center text-[0.6875rem] whitespace-normal"
        >
          {t("badge")}
        </Badge>
        <h1
          id="hero-titel"
          className="azm-display text-balance text-[2.25rem] sm:text-5xl lg:text-[3.5rem]"
        >
          {t("titel")}
        </h1>
        <p className="max-w-2xl text-pretty text-base leading-relaxed text-azm-ink-secondary sm:text-lg">
          {t("untertitel")}
        </p>
        {/*
          The two tracks, in the order a stranger can actually use them. Primary is the
          demo, which needs no account and takes no upload; secondary is the gated pilot.
          A "kostenlos testen" button aimed at `signup` would send most visitors to a form
          that refuses them — `SIGNUP_ALLOWLIST` gates it — which is a worse first
          impression than not offering it.
        */}
        <div className="mt-2 flex w-full flex-col gap-3 sm:w-auto sm:flex-row">
          <ButtonLink external href={links.demo} size="lg">
            {t("ctaPrimaer")}
            <ArrowRightIcon data-icon="inline-end" />
          </ButtonLink>
          <ButtonLink external href={links.signup} size="lg" variant="outline">
            {t("ctaSekundaer")}
          </ButtonLink>
        </div>
        <TrustBadges className="mt-4" />
        <p className="max-w-xl text-xs leading-relaxed text-muted-foreground">
          {t("hinweis")}
        </p>
      </div>
    </Section>
  );
}

/* --- 2. The problem ----------------------------------------------------------- */

function Problem() {
  const t = useTranslations("startseite.problem");
  const points = t.raw("punkte") as Titled[];

  return (
    <Section tone="soft" className="border-y border-azm-hairline">
      <SectionHeading
        eyebrow={t("eyebrow")}
        title={t("titel")}
        subtitle={t("untertitel")}
      />
      <ul className="mt-14 grid gap-6 md:grid-cols-3">
        {points.map((point, index) => {
          const Icon = PROBLEM_ICONS[index] ?? TriangleAlertIcon;
          return (
            <li key={point.titel}>
              <Card className="h-full bg-white">
                <CardHeader>
                  <Icon aria-hidden="true" className="mb-3 size-5 text-azm-ruby" />
                  <CardHeading className="text-lg">{point.titel}</CardHeading>
                </CardHeader>
                <CardContent className="leading-relaxed text-muted-foreground">
                  {point.text}
                </CardContent>
              </Card>
            </li>
          );
        })}
      </ul>
    </Section>
  );
}

/* --- 3. How it works ---------------------------------------------------------- */

function Workflow() {
  const t = useTranslations("startseite.ablauf");
  const steps = t.raw("schritte") as Titled[];

  return (
    <Section id="loesung">
      <SectionHeading
        eyebrow={t("eyebrow")}
        title={t("titel")}
        subtitle={t("untertitel")}
      />
      <ol className="mt-14 grid gap-6 md:grid-cols-3">
        {steps.map((step, index) => {
          const Icon = STEP_ICONS[index] ?? FileCheckIcon;
          return (
            <li key={step.titel} className="relative">
              <Card className="h-full ring-1 ring-azm-hairline">
                <CardHeader>
                  <div className="mb-3 flex items-center gap-3">
                    <span className="flex size-9 items-center justify-center rounded-full bg-primary/10 text-primary">
                      <Icon aria-hidden="true" className="size-4.5" />
                    </span>
                    <span
                      aria-hidden="true"
                      className="azm-tnum text-xs font-medium text-muted-foreground"
                    >
                      Schritt {index + 1}
                    </span>
                  </div>
                  <CardHeading className="text-lg">{step.titel}</CardHeading>
                </CardHeader>
                <CardContent className="leading-relaxed text-muted-foreground">
                  {/*
                    Step 2 is the only string on this page carrying live engine figures.
                    They come from `engineFacts`, which the engine's own test suite pins
                    to what the pipeline computes — see the module for why a number in
                    marketing prose is otherwise a claim with no way to stay true.
                  */}
                  {t(`schritte.${index}.text`, {
                    regeln: engineFacts.regelnDurchgesetzt,
                    laufzeit: engineFacts.laufzeitMs,
                  })}
                </CardContent>
              </Card>
            </li>
          );
        })}
      </ol>
    </Section>
  );
}

/* --- 4. The three buckets ----------------------------------------------------- */

function Buckets() {
  const t = useTranslations("startseite.buckets");
  const columns = t.raw("spalten") as Titled[];

  return (
    <Section tone="soft" className="border-y border-azm-hairline">
      <SectionHeading
        eyebrow={t("eyebrow")}
        title={t("titel")}
        subtitle={t("untertitel")}
      />

      <ul className="mt-14 grid gap-6 md:grid-cols-3">
        {columns.map((column, index) => {
          const bucket = BUCKETS[index] ?? BUCKETS[0]!;
          const Icon = bucket.icon;
          return (
            <li key={column.titel}>
              <div
                className={`flex h-full flex-col overflow-hidden rounded-xl ring-1 ${bucket.ring} bg-white`}
              >
                <div aria-hidden="true" className={`h-1 w-full ${bucket.bar}`} />
                <div className={`flex-1 p-8 ${bucket.surface}`}>
                  <div className="flex items-center gap-2.5">
                    <Icon aria-hidden="true" className={`size-5 ${bucket.accent}`} />
                    <h3 className={`text-lg font-medium ${bucket.accent}`}>
                      {column.titel}
                    </h3>
                  </div>
                  <p className="mt-3 leading-relaxed text-azm-ink-secondary">
                    {column.text}
                  </p>
                </div>
              </div>
            </li>
          );
        })}
      </ul>

      {/*
        The claim the three columns exist to support, and the number that makes it
        credible. They sit together on one panel on purpose: "we do not guess" is a
        slogan until it is followed by the share of the catalogue we cannot judge.
      */}
      <div className="mt-10 grid gap-6 lg:grid-cols-2">
        <div className="rounded-xl bg-azm-navy p-8 text-white">
          <h3 className="text-lg font-medium">{t("kernaussageTitel")}</h3>
          <p className="mt-3 leading-relaxed text-white/75">{t("kernaussage")}</p>
        </div>
        <div className="rounded-xl bg-white p-8 ring-1 ring-azm-hairline">
          <h3 className="text-lg font-medium">{t("ehrlichkeitTitel")}</h3>
          <p className="azm-tnum mt-3 leading-relaxed text-azm-ink-secondary">
            {t("ehrlichkeit", {
              katalogGeprueft: engineFacts.katalogGeprueft,
              katalogZiffern: engineFacts.katalogZiffern,
              katalogAnteil: engineFacts.katalogAnteil,
            })}
          </p>
        </div>
      </div>
    </Section>
  );
}

/* --- 5. Features -------------------------------------------------------------- */

function Features() {
  const t = useTranslations("startseite.funktionen");
  const features = t.raw("punkte") as Titled[];

  /* Interpolated into both the title and the body of the rule-count card. */
  const values = {
    regeln: engineFacts.regelnDurchgesetzt,
    regelnGesamt: engineFacts.regelnGesamt,
    anteil: engineFacts.regelnAnteil,
    laufzeit: engineFacts.laufzeitMs,
  };

  return (
    <Section id="funktionen">
      <SectionHeading
        eyebrow={t("eyebrow")}
        title={t("titel")}
        subtitle={t("untertitel")}
      />
      <ul className="mt-14 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
        {/* The raw array supplies the count and the order; every string is read by index
            through `t()` so the placeholders in it are interpolated. */}
        {features.map((_feature, index) => {
          const Icon = FEATURE_ICONS[index] ?? FileCheckIcon;
          return (
            /*
              Keyed by position, not by title: one of these titles carries an ICU
              placeholder (`{regeln}`), and using the raw string would put an
              uninterpolated token into the RSC payload as a DOM key.
            */
            <li key={`funktion-${index}`}>
              <Card className="h-full ring-1 ring-azm-hairline">
                <CardHeader>
                  <Icon aria-hidden="true" className="mb-3 size-5 text-primary" />
                  <CardHeading className="azm-tnum text-lg">
                    {t(`punkte.${index}.titel`, values)}
                  </CardHeading>
                </CardHeader>
                <CardContent className="leading-relaxed text-muted-foreground">
                  {t(`punkte.${index}.text`, values)}
                </CardContent>
              </Card>
            </li>
          );
        })}
      </ul>
    </Section>
  );
}

/* --- 6. Who it is for --------------------------------------------------------- */

function Audiences() {
  const t = useTranslations("startseite.zielgruppen");
  const cards = t.raw("karten") as Audience[];
  const links = getProductLinks();

  /*
   * One destination per audience, in the same order as the catalogue: the billing
   * centre wants the pilot, the vendor wants the contract, the physician wants to see
   * it run. Three cards that all pointed at the same button would be a layout, not a
   * qualification.
   */
  const destinations = [
    { href: links.signup, external: true },
    { href: routes.api, external: false },
    { href: links.demo, external: true },
  ] as const;

  return (
    <Section tone="soft" className="border-y border-azm-hairline">
      <SectionHeading
        eyebrow={t("eyebrow")}
        title={t("titel")}
        subtitle={t("untertitel")}
      />
      <ul className="mt-14 grid gap-6 md:grid-cols-3">
        {cards.map((card, index) => {
          const Icon = AUDIENCE_ICONS[index] ?? BuildingIcon;
          const destination = destinations[index] ?? destinations[0];
          return (
            <li key={card.titel}>
              <Card className="flex h-full flex-col bg-white">
                <CardHeader>
                  <Icon aria-hidden="true" className="mb-3 size-5 text-primary" />
                  <CardHeading className="text-lg">{card.titel}</CardHeading>
                </CardHeader>
                <CardContent className="flex flex-1 flex-col items-start gap-5 leading-relaxed text-muted-foreground">
                  <p className="flex-1">{card.text}</p>
                  <ButtonLink
                    external={destination.external}
                    href={destination.href}
                    variant="outline"
                    size="sm"
                  >
                    {card.cta}
                    <ArrowRightIcon data-icon="inline-end" />
                  </ButtonLink>
                </CardContent>
              </Card>
            </li>
          );
        })}
      </ul>
    </Section>
  );
}

/* --- 7. The pilot programme --------------------------------------------------- */

function Pilot() {
  const t = useTranslations("startseite.pilot");
  const points = t.raw("punkte") as string[];
  const links = getProductLinks();

  return (
    <Section id="pilot" tone="cream">
      <div className="grid items-start gap-10 lg:grid-cols-2 lg:gap-16">
        <div>
          <SectionHeading
            eyebrow={t("eyebrow")}
            title={t("titel")}
            subtitle={t("text")}
            align="start"
          />
          <div className="mt-8 flex flex-col gap-3 sm:flex-row">
            <ButtonLink external href={links.signup} size="lg">
              {t("cta")}
              <ArrowRightIcon data-icon="inline-end" />
            </ButtonLink>
            <ButtonLink external href={links.demo} size="lg" variant="outline">
              {t("ctaSekundaer")}
            </ButtonLink>
          </div>
        </div>

        <div className="rounded-xl bg-white/70 p-8 ring-1 ring-azm-ink/10">
          <ul className="flex flex-col gap-4">
            {points.map((point) => (
              <li key={point} className="flex items-start gap-3">
                <CheckIcon
                  aria-hidden="true"
                  className="mt-0.5 size-4.5 shrink-0 text-primary"
                />
                <span className="leading-relaxed text-azm-ink-secondary">{point}</span>
              </li>
            ))}
          </ul>
          <p className="mt-6 border-t border-azm-ink/10 pt-6 text-xs leading-relaxed text-azm-ink-secondary/80">
            {t("hinweis")}
          </p>
        </div>
      </div>
    </Section>
  );
}

/* --- 8. For developers -------------------------------------------------------- */

function ApiTeaser() {
  const t = useTranslations("startseite.api");

  return (
    <Section tone="navy" id="api">
      <div className="grid items-center gap-10 lg:grid-cols-2 lg:gap-16">
        <div>
          <p className="text-[0.6875rem] font-medium tracking-[0.12em] text-white/50 uppercase">
            {t("eyebrow")}
          </p>
          <h2 className="azm-display mt-4 text-balance text-[2rem] sm:text-[2.5rem]">
            {t("titel")}
          </h2>
          <p className="mt-4 leading-relaxed text-white/75">{t("text")}</p>
          <div className="mt-8 flex flex-col gap-3 sm:flex-row">
            <ButtonLink href={routes.api} size="lg" variant="secondary">
              {t("cta")}
              <ArrowRightIcon data-icon="inline-end" />
            </ButtonLink>
            {/*
              `rel="noreferrer"` alongside `noopener`: the destination is a different
              origin, and there is no reason to hand it this site's referrer.
            */}
            <a
              href={apiDocsUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex h-10 items-center justify-center rounded-full border border-white/25 px-4 text-sm font-medium whitespace-nowrap text-white transition-colors hover:bg-white/10"
            >
              {t("ctaSekundaer")}
            </a>
          </div>
        </div>

        <CodeBlock
          code={CURL_EXAMPLE}
          label={t("snippetLabel")}
          copyLabel={t("kopieren")}
          copiedLabel={t("kopiert")}
        />
      </div>
    </Section>
  );
}

/* --- Closing ------------------------------------------------------------------ */

function ClosingCta() {
  const t = useTranslations("startseite.cta");
  const links = getProductLinks();

  return (
    <Section tone="soft" className="border-t border-azm-hairline">
      <div className="rounded-2xl bg-white px-6 py-14 text-center ring-1 ring-azm-hairline sm:px-12">
        <SectionHeading title={t("titel")} subtitle={t("text")} />
        <div className="mt-8 flex flex-col justify-center gap-3 sm:flex-row">
          <ButtonLink external href={links.demo} size="lg">
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
