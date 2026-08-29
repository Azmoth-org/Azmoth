import type { Metadata } from "next";
import { useTranslations } from "next-intl";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { ArrowRightIcon, CheckIcon } from "lucide-react";

import { Button } from "@workspace/ui/components/button";
import { Card, CardContent, CardHeader, CardTitle } from "@workspace/ui/components/card";

import { Section, SectionHeading } from "@/components/section";
import { buildPageMetadata } from "@/lib/seo";
import { siteConfig } from "@/lib/site";

type Group = { titel: string; punkte: string[] };

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "metadaten" });

  return buildPageMetadata({
    path: "/funktionen",
    title: t("funktionenTitel"),
    description: t("funktionenBeschreibung"),
  });
}

export default async function FunktionenPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);

  return (
    <>
      <FeatureGroups />
      <FeatureCta />
    </>
  );
}

function FeatureGroups() {
  const t = useTranslations("funktionen");
  const groups = t.raw("gruppen") as Group[];

  return (
    <Section className="pt-16 lg:pt-24">
      <SectionHeading title={t("titel")} subtitle={t("untertitel")} as="h1" />
      <div className="mt-14 grid gap-6 md:grid-cols-2">
        {groups.map((group) => (
          <Card key={group.titel} className="h-full">
            <CardHeader>
              <CardTitle className="text-lg">{group.titel}</CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="flex flex-col gap-3">
                {group.punkte.map((point) => (
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
        ))}
      </div>
    </Section>
  );
}

function FeatureCta() {
  const t = useTranslations("funktionen.cta");

  return (
    <Section className="border-t border-border/60">
      <div className="flex flex-col items-center gap-6 text-center">
        <SectionHeading title={t("titel")} subtitle={t("text")} />
        <Button size="lg" render={<a href={siteConfig.signup} />}>
          {t("primaer")}
          <ArrowRightIcon data-icon="inline-end" />
        </Button>
      </div>
    </Section>
  );
}
