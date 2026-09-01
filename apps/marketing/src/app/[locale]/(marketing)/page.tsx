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

import { AuroraBackground } from "@workspace/ui/components/aurora-background";
import { Badge } from "@workspace/ui/components/badge";
import { Card, CardContent, CardHeader } from "@workspace/ui/components/card";
import { cn } from "@workspace/ui/lib/utils";

import { ButtonLink } from "@/components/button-link";
import { CardHeading } from "@/components/card-heading";
import { CodeBlock } from "@/components/code-block";
import { GradientMesh } from "@/components/gradient-mesh";
import { HeroMockup } from "@/components/hero-mockup";
import { Reveal, RevealGroup, RevealItem } from "@/components/reveal";
import { Section, SectionHeading } from "@/components/section";
import { TrustBadges } from "@/components/trust-badges";
import { CURL_EXAMPLE } from "@/lib/api-example";
import { engineFacts } from "@/lib/engine-facts";
import { buildPageMetadata } from "@/lib/seo";
import { apiDocsUrl, getDocsUrl, getProductLinks, routes, siteConfig } from "@/lib/site";

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
      <TrustBand />
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

/**
 * Three backdrop layers, and each earns its place rather than being stacked for effect.
 *
 * `AuroraBackground` drifts (60s per cycle, composited), `.azm-grid` rules the space behind the
 * mockup, and `GradientMesh` is `DESIGN.md`'s signature wash over the top of both. Order matters:
 * the mesh must be last so the brand's own colour is what a visitor actually registers, with the
 * other two reading as depth underneath it rather than as competing washes.
 *
 * All three are pure CSS — no image request on the critical path, and nothing that can shift the
 * layout once it lands. The hero's Largest Contentful Paint is the H1, and it paints on the first
 * frame with the backdrop composited around it.
 */
function HeroBackdrop() {
  return (
    <>
      <AuroraBackground />
      <div aria-hidden="true" className="azm-grid" />
      <GradientMesh />
    </>
  );
}

function Hero() {
  const t = useTranslations("startseite.hero");
  const links = getProductLinks();

  return (
    <Section
      className="pt-16 pb-20 lg:pt-24 lg:pb-32"
      backdrop={<HeroBackdrop />}
      aria-labelledby="hero-titel"
    >
      <div className="mx-auto flex max-w-4xl flex-col items-center gap-6 text-center">
        {/*
          `.azm-enter` and an inline delay, not `<Reveal>`.

          Two reasons, and the second is the one that decides it. Above the fold there is no
          viewport threshold to cross, so a scroll observer has nothing to observe — the stagger
          here is an entrance sequence, not a response to anything. And the `<h1>` below is this
          page's Largest Contentful Paint: rendering it at `opacity: 0` until `motion` hydrates
          moves LCP from 320 ms to 1050 ms on the production build, for a fade. See `.azm-enter` in
          globals.css. It also keeps the entire hero a server component.
        */}
        <div className="azm-enter">
          {/*
            `whitespace-normal` and `h-auto` undo two of Badge's defaults on purpose. The
            shared component is built for a one-word status chip, so it is a fixed-height
            `whitespace-nowrap` pill; this eyebrow is a sixty-character German noun phrase
            and at 390px it was 424px wide, which is the whole of the mobile page's
            horizontal overflow. It wraps to two lines instead.
          */}
          <Badge
            variant="secondary"
            className="azm-glass h-auto max-w-full px-3 py-1 text-center text-[0.6875rem] whitespace-normal"
          >
            {t("badge")}
          </Badge>
        </div>

        {/*
          The headline does not animate. Everything around it does.

          This started as a fade like its neighbours, and both versions of that were wrong. As a
          `<Reveal>` it waited for hydration and pushed Largest Contentful Paint from 320 ms to
          1050 ms. Rewritten as a CSS entrance it was fast, and it fell out of the metric
          altogether: Chrome fixes an element's LCP candidacy at its *first* paint, so something
          rendered at `opacity: 0` is excluded permanently, however quickly it fades up afterwards.
          LCP then reported a 2 900 px² link as this page's largest content, which is not a measure
          of anything — the number improves while the headline appears no sooner.

          Painting it immediately is the version that is fast rather than the version that measures
          fast, and it is also what the sites this brief names actually do: the display type is
          there in the first frame and the chrome assembles around it. Measured: LCP 340 ms, on the
          `<h1>`, which is the element a reader is actually waiting for.
        */}
        <div>
          <h1
            id="hero-titel"
            /*
              `text-balance` rather than `react-wrap-balancer`, which the brief suggested. They
              solve the same problem — a headline whose last line is one orphaned word — and the
              CSS property does it in the layout engine, on the frame the text is measured. The
              library does it in JavaScript after hydration, which on the largest contentful
              element on the page means a visible re-wrap and a Cumulative Layout Shift the brief
              also asks to keep at zero. `text-wrap: balance` has been in every major engine since
              2023; the library exists for the years before that.
            */
            className="azm-display text-[2.25rem] text-balance sm:text-5xl lg:text-[3.5rem]"
          >
            {t("titel")}
          </h1>
        </div>

        <div className="azm-enter" style={{ "--azm-enter-delay": "120ms" } as React.CSSProperties}>
          <p className="max-w-2xl text-base leading-relaxed text-pretty text-azm-ink-secondary sm:text-lg">
            {t("untertitel")}
          </p>
        </div>

        {/*
          The two tracks, in the order a stranger can actually use them. Primary is the
          demo, which needs no account and takes no upload; secondary is the gated pilot.
          A "kostenlos testen" button aimed at `signup` would send most visitors to a form
          that refuses them — `SIGNUP_ALLOWLIST` gates it — which is a worse first
          impression than not offering it.
        */}
        <div
          className="azm-enter mt-2 w-full sm:w-auto"
          style={{ "--azm-enter-delay": "180ms" } as React.CSSProperties}
        >
          <div className="flex w-full flex-col gap-3 sm:w-auto sm:flex-row">
            <ButtonLink external href={links.demo} size="lg">
              {t("ctaPrimaer")}
              <ArrowRightIcon data-icon="inline-end" />
            </ButtonLink>
            <ButtonLink
              external
              href={links.signup}
              size="lg"
              variant="outline"
              className="azm-glass"
            >
              {t("ctaSekundaer")}
            </ButtonLink>
          </div>
        </div>

        <div className="azm-enter" style={{ "--azm-enter-delay": "240ms" } as React.CSSProperties}>
          <p className="max-w-xl text-xs leading-relaxed text-muted-foreground">
            {t("hinweis")}
          </p>
        </div>
      </div>

      {/*
        The mockup arrives last and travels furthest, because it is the only element here that a
        visitor has to *look at* rather than read. Delaying it past the headline means the eye
        settles on the claim before the evidence for it slides up underneath.
      */}
      <div
        className="azm-enter mx-auto mt-14 max-w-4xl lg:mt-20"
        style={{ "--azm-enter-delay": "300ms" } as React.CSSProperties}
      >
        <HeroMockup />
      </div>
    </Section>
  );
}

/* --- 2. Trust band ------------------------------------------------------------ */

/**
 * A quiet band between the hero and the argument.
 *
 * It is deliberately the least designed thing on the page. Every claim in it is checkable —
 * hosting region, the pilot's data rule, the absence of a language model — and a compliance
 * statement rendered with the same weight as a call to action reads as marketing rather than as
 * fact. The band exists to be scanned in a second and believed, not to be admired.
 */
function TrustBand() {
  const t = useTranslations("vertrauen");

  return (
    <Section tone="soft" className="border-y border-azm-hairline py-10 lg:py-12">
      <Reveal className="flex flex-col items-center gap-6">
        <p className="text-[0.6875rem] font-medium tracking-[0.12em] text-azm-ink-mute uppercase">
          {t("bandTitel")}
        </p>
        <TrustBadges />
      </Reveal>
    </Section>
  );
}

/* --- 3. The problem ----------------------------------------------------------- */

/**
 * A bento grid rather than three equal columns.
 *
 * The first point is the one a billing centre already agrees with before it arrives — manual
 * review costs time — so it takes the wide cell and carries the section. The other two are the
 * reasons they have not solved it yet and sit beside it at half the width. Three identical cards
 * would give equal visual weight to three claims that do not have equal weight.
 */
function Problem() {
  const t = useTranslations("startseite.problem");
  const points = t.raw("punkte") as Titled[];

  return (
    <Section>
      <SectionHeading
        eyebrow={t("eyebrow")}
        title={t("titel")}
        subtitle={t("untertitel")}
      />
      <RevealGroup
        as="ul"
        className="mt-14 grid gap-4 sm:gap-6 lg:grid-cols-2 lg:grid-rows-2"
      >
        {points.map((point, index) => {
          const Icon = PROBLEM_ICONS[index] ?? TriangleAlertIcon;
          const isLead = index === 0;
          return (
            <RevealItem key={point.titel} className={isLead ? "lg:row-span-2" : undefined}>
              {/*
                The lead cell centres its content vertically. Without it a two-line body floats at
                the top of a cell twice its height, which is the failure mode that makes a bento
                grid read as an ordinary grid with a hole in it.
              */}
              <Card
                className={cn(
                  "azm-lift h-full bg-white ring-1 ring-azm-hairline",
                  isLead && "flex flex-col justify-center p-2 sm:p-4"
                )}
              >
                <CardHeader>
                  <span
                    className={cn(
                      "mb-3 flex items-center justify-center rounded-xl bg-azm-ruby/10 text-azm-ruby",
                      isLead ? "size-12" : "size-10"
                    )}
                  >
                    <Icon aria-hidden="true" className={isLead ? "size-6" : "size-5"} />
                  </span>
                  <CardHeading className={isLead ? "text-display-md" : "text-lg"}>
                    {point.titel}
                  </CardHeading>
                </CardHeader>
                <CardContent
                  className={cn(
                    "leading-relaxed text-muted-foreground",
                    isLead && "sm:text-lg"
                  )}
                >
                  {point.text}
                </CardContent>
              </Card>
            </RevealItem>
          );
        })}
      </RevealGroup>
    </Section>
  );
}

/* --- 4. How it works ---------------------------------------------------------- */

function Workflow() {
  const t = useTranslations("startseite.ablauf");
  const steps = t.raw("schritte") as Titled[];

  return (
    <Section id="loesung" tone="soft" className="border-y border-azm-hairline">
      <SectionHeading
        eyebrow={t("eyebrow")}
        title={t("titel")}
        subtitle={t("untertitel")}
      />
      <RevealGroup as="ol" className="mt-14 grid gap-6 md:grid-cols-3">
        {steps.map((step, index) => {
          const Icon = STEP_ICONS[index] ?? FileCheckIcon;
          return (
            <RevealItem key={step.titel}>
              <Card className="azm-lift h-full bg-white ring-1 ring-azm-hairline">
                <CardHeader>
                  <div className="mb-3 flex items-center gap-3">
                    <span className="flex size-10 items-center justify-center rounded-xl bg-primary/10 text-primary">
                      <Icon aria-hidden="true" className="size-5" />
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
            </RevealItem>
          );
        })}
      </RevealGroup>
    </Section>
  );
}

/* --- 5. The three buckets ----------------------------------------------------- */

/**
 * `id="kategorien"` — the navigation's "Drei-Kategorien-Modell" entry links here, and the section
 * is the product's central differentiator, so it is worth a stable anchor of its own.
 */
function Buckets() {
  const t = useTranslations("startseite.buckets");
  const columns = t.raw("spalten") as Titled[];

  return (
    <Section id="kategorien">
      <SectionHeading
        eyebrow={t("eyebrow")}
        title={t("titel")}
        subtitle={t("untertitel")}
      />

      <RevealGroup as="ul" className="mt-14 grid gap-6 md:grid-cols-3">
        {columns.map((column, index) => {
          const bucket = BUCKETS[index] ?? BUCKETS[0]!;
          const Icon = bucket.icon;
          return (
            <RevealItem key={column.titel}>
              <div
                className={`azm-lift flex h-full flex-col overflow-hidden rounded-xl ring-1 ${bucket.ring} bg-white`}
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
                  {/*
                    The statute chip, on the middle column only. "Nachweislich falsch" is the one
                    verdict that has to be *shown* rather than asserted: the difference between
                    this product and a risk score is that a rejection arrives with the paragraph
                    it follows from, and a reader who scans three cards should see that difference
                    without reading a word of the body copy.
                  */}
                  {index === 1 ? (
                    <code className="azm-tnum mt-4 inline-block rounded-md bg-azm-wrong/10 px-2 py-1 text-xs font-medium text-azm-wrong">
                      § 4 Abs. 2a GOÄ
                    </code>
                  ) : null}
                </div>
              </div>
            </RevealItem>
          );
        })}
      </RevealGroup>

      {/*
        The claim the three columns exist to support, and the number that makes it
        credible. They sit together on one panel on purpose: "we do not guess" is a
        slogan until it is followed by the share of the catalogue we cannot judge.
      */}
      <RevealGroup className="mt-10 grid gap-6 lg:grid-cols-2">
        <RevealItem as="div">
          <div className="relative h-full overflow-hidden rounded-xl bg-azm-navy p-8 text-white">
            {/* The aurora, unmasked and dim, as the dark panel's own atmosphere. */}
            <AuroraBackground showRadialGradient={false} className="opacity-40" />
            <div className="relative">
              <h3 className="text-lg font-medium">{t("kernaussageTitel")}</h3>
              <p className="mt-3 leading-relaxed text-white/75">{t("kernaussage")}</p>
            </div>
          </div>
        </RevealItem>
        <RevealItem as="div">
          <div className="h-full rounded-xl bg-white p-8 ring-1 ring-azm-hairline">
            <h3 className="text-lg font-medium">{t("ehrlichkeitTitel")}</h3>
            <p className="azm-tnum mt-3 leading-relaxed text-azm-ink-secondary">
              {t("ehrlichkeit", {
                katalogGeprueft: engineFacts.katalogGeprueft,
                katalogZiffern: engineFacts.katalogZiffern,
                katalogAnteil: engineFacts.katalogAnteil,
              })}
            </p>
          </div>
        </RevealItem>
      </RevealGroup>
    </Section>
  );
}

/* --- 6. Features -------------------------------------------------------------- */

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
    <Section id="funktionen" tone="soft" className="border-y border-azm-hairline">
      <SectionHeading
        eyebrow={t("eyebrow")}
        title={t("titel")}
        subtitle={t("untertitel")}
      />
      <RevealGroup as="ul" className="mt-14 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
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
            <RevealItem key={`funktion-${index}`}>
              <Card className="azm-lift h-full bg-white ring-1 ring-azm-hairline">
                <CardHeader>
                  <span className="mb-3 flex size-10 items-center justify-center rounded-xl bg-primary/10 text-primary">
                    <Icon aria-hidden="true" className="size-5" />
                  </span>
                  <CardHeading className="azm-tnum text-lg">
                    {t(`punkte.${index}.titel`, values)}
                  </CardHeading>
                </CardHeader>
                <CardContent className="leading-relaxed text-muted-foreground">
                  {t(`punkte.${index}.text`, values)}
                </CardContent>
              </Card>
            </RevealItem>
          );
        })}
      </RevealGroup>
    </Section>
  );
}

/* --- 7. Who it is for --------------------------------------------------------- */

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
    // The vendor's card now leaves this origin: the API documentation is `apps/docs`.
    { href: getDocsUrl(), external: true },
    { href: links.demo, external: true },
  ] as const;

  return (
    <Section>
      <SectionHeading
        eyebrow={t("eyebrow")}
        title={t("titel")}
        subtitle={t("untertitel")}
      />
      <RevealGroup as="ul" className="mt-14 grid gap-6 md:grid-cols-3">
        {cards.map((card, index) => {
          const Icon = AUDIENCE_ICONS[index] ?? BuildingIcon;
          const destination = destinations[index] ?? destinations[0];
          return (
            <RevealItem key={card.titel}>
              <Card className="azm-lift flex h-full flex-col bg-white ring-1 ring-azm-hairline">
                <CardHeader>
                  <span className="mb-3 flex size-10 items-center justify-center rounded-xl bg-primary/10 text-primary">
                    <Icon aria-hidden="true" className="size-5" />
                  </span>
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
            </RevealItem>
          );
        })}
      </RevealGroup>
    </Section>
  );
}

/* --- 8. The pilot programme --------------------------------------------------- */

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
          <Reveal delay={0.1} className="mt-8">
            <div className="flex flex-col gap-3 sm:flex-row">
              <ButtonLink external href={links.signup} size="lg">
                {t("cta")}
                <ArrowRightIcon data-icon="inline-end" />
              </ButtonLink>
              <ButtonLink external href={links.demo} size="lg" variant="outline">
                {t("ctaSekundaer")}
              </ButtonLink>
            </div>
          </Reveal>
        </div>

        <Reveal delay={0.1}>
          {/*
            `.azm-glass` on the cream band rather than `bg-white/70`. The band is the one warm
            surface on the site, and a flat translucent white over it goes grey; the glass tints
            and blurs what is behind it instead, so the cream reads through the panel.
          */}
          <div className="azm-glass rounded-2xl p-8">
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
            <div className="mt-6 space-y-3 border-t border-azm-ink/10 pt-6 text-xs leading-relaxed text-azm-ink-secondary/80">
              <p>{t("hinweis")}</p>
              {/*
                The scope of the pilot, said where a partner decides what to export rather than
                after they have exported it. Azmoth prices against the current GOÄ — the only
                catalog edition holding real numbers — so an invoice from three years ago is
                measured against a fee schedule that did not apply on the day of treatment. It is
                still audited, and the report says so; asking for twelve months here is what keeps
                that from being a surprise. `/faq` carries the same statement as a question.
              */}
              <p>{t("hinweisKatalog")}</p>
            </div>
          </div>
        </Reveal>
      </div>
    </Section>
  );
}

/* --- 9. For developers -------------------------------------------------------- */

function ApiTeaser() {
  const t = useTranslations("startseite.api");

  return (
    <Section tone="navy" id="api" backdrop={<AuroraBackground showRadialGradient={false} />}>
      <div className="grid items-center gap-10 lg:grid-cols-2 lg:gap-16">
        <Reveal>
          <p className="text-[0.6875rem] font-medium tracking-[0.12em] text-white/50 uppercase">
            {t("eyebrow")}
          </p>
          <h2 className="azm-display mt-4 text-[2rem] text-balance sm:text-[2.5rem]">
            {t("titel")}
          </h2>
          <p className="mt-4 leading-relaxed text-white/75">{t("text")}</p>
          <div className="mt-8 flex flex-col gap-3 sm:flex-row">
            <ButtonLink href={getDocsUrl()} external size="lg" variant="secondary">
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
        </Reveal>

        <Reveal delay={0.1}>
          <CodeBlock
            code={CURL_EXAMPLE}
            label={t("snippetLabel")}
            copyLabel={t("kopieren")}
            copiedLabel={t("kopiert")}
          />
        </Reveal>
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
      <div className="relative overflow-hidden rounded-3xl bg-white px-6 py-16 text-center ring-1 ring-azm-hairline sm:px-12">
        <GradientMesh />
        <div className="relative">
          <SectionHeading title={t("titel")} subtitle={t("text")} />
          <Reveal delay={0.1} className="mt-8">
            <div className="flex flex-col justify-center gap-3 sm:flex-row">
              <ButtonLink external href={links.demo} size="lg">
                {t("primaer")}
                <ArrowRightIcon data-icon="inline-end" />
              </ButtonLink>
              <ButtonLink href={routes.kontakt} size="lg" variant="outline">
                {t("sekundaer")}
              </ButtonLink>
            </div>
          </Reveal>
        </div>
      </div>
    </Section>
  );
}
