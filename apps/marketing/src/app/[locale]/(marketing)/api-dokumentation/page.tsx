import type { Metadata } from "next";
import { useTranslations } from "next-intl";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { ArrowRightIcon, InfoIcon } from "lucide-react";

import {Card, CardContent, CardHeader} from "@workspace/ui/components/card";

import { CodeBlock } from "@/components/code-block";
import { CardHeading } from "@/components/card-heading";
import { Section, SectionHeading } from "@/components/section";
import { CURL_EXAMPLE, RESPONSE_EXAMPLE } from "@/lib/api-example";
import { buildPageMetadata } from "@/lib/seo";
import { apiContractUrl } from "@/lib/site";

/**
 * The integrator's landing page — orientation, not the contract.
 *
 * `docs/api/PARTNER_API.md` is the contract, it is versioned alongside the engine that
 * implements it, and its worked example is pinned by a test that fails the build when
 * the engine's figures move. Restating any of that here creates a second copy with none
 * of those guarantees, which by the third release says something different. So this page
 * does the three things a document in a repository does badly — orient, show one call
 * that works, and name the two constraints that bite early — and then links out.
 */

type Step = { titel: string; text: string };

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "metadaten" });

  return buildPageMetadata({
    path: "/api-dokumentation",
    title: t("apiTitel"),
    description: t("apiBeschreibung"),
    keywords: ["GOÄ API", "PADnext API", "PVS Integration", "REST API", "Abrechnungsprüfung"],
  });
}

export default async function ApiPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  return <ApiContent />;
}

function ApiContent() {
  const t = useTranslations("apiSeite");
  const tHome = useTranslations("startseite.api");
  const steps = t.raw("schritte") as Step[];
  const notes = t.raw("hinweise") as string[];

  return (
    <>
      <Section className="pt-16 lg:pt-24">
        <SectionHeading title={t("titel")} subtitle={t("untertitel")} align="start" as="h1" />

        {/*
          `min-w-0` on both columns.

          A grid item's automatic minimum size is its min-content width, and `CardHeader`
          carries `@container/card-header` — an inline-size container, whose width is by
          definition computed independently of what is inside it. Inside an
          intrinsically-sized track that combination stopped resolving to anything the
          column could shrink to: at 390px these two columns measured 758px wide and took
          the whole page into horizontal scroll. `min-w-0` opts the items out of the
          automatic minimum, which is what lets the track govern the width instead.
        */}
        <div className="mt-12 grid gap-10 lg:grid-cols-[1fr_1.1fr] lg:gap-14">
          <ol className="flex min-w-0 flex-col gap-6">
            {steps.map((step) => (
              <li key={step.titel}>
                <Card className="ring-1 ring-azm-hairline">
                  <CardHeader>
                    <CardHeading className="text-lg">{step.titel}</CardHeading>
                  </CardHeader>
                  <CardContent className="leading-relaxed text-muted-foreground">
                    {step.text}
                  </CardContent>
                </Card>
              </li>
            ))}
          </ol>

          <div className="flex min-w-0 flex-col gap-6">
            <CodeBlock
              code={CURL_EXAMPLE}
              label={t("snippetLabel")}
              copyLabel={tHome("kopieren")}
              copiedLabel={tHome("kopiert")}
            />
            <CodeBlock
              code={RESPONSE_EXAMPLE}
              label={t("antwortLabel")}
              copyLabel={tHome("kopieren")}
              copiedLabel={tHome("kopiert")}
            />
          </div>
        </div>
      </Section>

      <Section tone="soft" className="border-y border-azm-hairline">
        <div className="grid gap-10 lg:grid-cols-2 lg:gap-16">
          <div>
            <h2 className="azm-display text-[2rem] text-balance sm:text-[2.5rem]">
              {t("hinweisTitel")}
            </h2>
            <ul className="mt-8 flex flex-col gap-5">
              {notes.map((note) => (
                <li key={note} className="flex items-start gap-3">
                  <InfoIcon
                    aria-hidden="true"
                    className="mt-0.5 size-4.5 shrink-0 text-primary"
                  />
                  <span className="leading-relaxed text-azm-ink-secondary">{note}</span>
                </li>
              ))}
            </ul>
          </div>

          <div className="rounded-xl bg-azm-navy p-8 text-white lg:self-start">
            <h2 className="text-lg font-medium">{t("vertragTitel")}</h2>
            <p className="mt-3 leading-relaxed text-white/75">{t("vertragText")}</p>
            <a
              href={apiContractUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-6 inline-flex h-10 items-center justify-center gap-1.5 rounded-full bg-white px-4 text-sm font-medium text-azm-navy transition-colors hover:bg-white/90"
            >
              {t("vertragCta")}
              <ArrowRightIcon aria-hidden="true" className="size-4" />
            </a>
          </div>
        </div>
      </Section>
    </>
  );
}
