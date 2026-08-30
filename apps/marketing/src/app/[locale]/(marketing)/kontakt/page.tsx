import type { Metadata } from "next";
import { useTranslations } from "next-intl";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { MailIcon, SendIcon } from "lucide-react";

import {Card, CardContent, CardHeader} from "@workspace/ui/components/card";

import { ButtonLink } from "@/components/button-link";
import { CardHeading } from "@/components/card-heading";
import { Section, SectionHeading } from "@/components/section";
import { buildPageMetadata } from "@/lib/seo";
import { getProductLinks, siteConfig } from "@/lib/site";

/**
 * Contact is a mail link, not a form.
 *
 * A form needs somewhere to post to, and this application deliberately has no
 * database, no mail credentials and no API routes — that was the point of Option A.
 * A form that silently drops enquiries is worse than an address that works, so
 * until a backend exists this page hands the visitor a real mailbox.
 *
 * The address comes from `siteConfig` rather than being typed here: it also appears in
 * the footer, the Impressum and the privacy notice, and a site offering three different
 * mailboxes is telling the visitor that nobody reads any of them.
 */

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "metadaten" });

  return buildPageMetadata({
    path: "/kontakt",
    title: t("kontaktTitel"),
    description: t("kontaktBeschreibung"),
  });
}

export default async function KontaktPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  return <KontaktContent />;
}

function KontaktContent() {
  const t = useTranslations("kontakt");

  return (
    <Section className="pt-16 lg:pt-24">
      <SectionHeading
        title={t("titel")}
        subtitle={t("untertitel")}
        align="start"
        as="h1"
      />

      <div className="mt-10 grid max-w-4xl gap-6 sm:grid-cols-2 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <MailIcon aria-hidden="true" className="mb-2 size-5 text-primary" />
            <CardHeading>{t("emailLabel")}</CardHeading>
          </CardHeader>
          <CardContent>
            <a
              href={`mailto:${siteConfig.email}`}
              className="text-primary underline underline-offset-4"
            >
              {siteConfig.email}
            </a>
          </CardContent>
        </Card>

        {/*
          The pilot ask, given a landing place that is not the gated signup form.
          `SIGNUP_ALLOWLIST` refuses anyone not already on the list, so every "Pilot-Zugang
          anfordern" button on the site needs somewhere a stranger can actually be heard —
          and this mailbox is it.
        */}
        <Card>
          <CardHeader>
            <SendIcon aria-hidden="true" className="mb-2 size-5 text-primary" />
            <CardHeading>{t("pilotTitel")}</CardHeading>
          </CardHeader>
          <CardContent className="flex flex-col items-start gap-4">
            <p className="leading-relaxed text-muted-foreground">{t("pilotText")}</p>
            <ButtonLink
              external
              href={`mailto:${siteConfig.email}?subject=${encodeURIComponent("Pilot-Zugang Azmoth")}`}
              size="sm"
            >
              {t("pilotCta")}
            </ButtonLink>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardHeading>{t("hinweisTitel")}</CardHeading>
          </CardHeader>
          <CardContent className="flex flex-col items-start gap-4">
            <p className="text-muted-foreground">{t("hinweisText")}</p>
            <ButtonLink external href={getProductLinks().login} variant="outline" size="sm">
              {t("hinweisCta")}
            </ButtonLink>
          </CardContent>
        </Card>
      </div>
    </Section>
  );
}
