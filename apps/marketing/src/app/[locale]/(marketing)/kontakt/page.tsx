import type { Metadata } from "next";
import { useTranslations } from "next-intl";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { MailIcon } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@workspace/ui/components/card";

import { ButtonLink } from "@/components/button-link";
import { Section, SectionHeading } from "@/components/section";
import { buildPageMetadata } from "@/lib/seo";
import { getProductLinks } from "@/lib/site";

/**
 * Contact is a mail link, not a form.
 *
 * A form needs somewhere to post to, and this application deliberately has no
 * database, no mail credentials and no API routes — that was the point of Option A.
 * A form that silently drops enquiries is worse than an address that works, so
 * until a backend exists this page hands the visitor a real mailbox.
 */
const CONTACT_EMAIL = "kontakt@azmoth.de";

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

      <div className="mt-10 grid max-w-3xl gap-6 sm:grid-cols-2">
        <Card>
          <CardHeader>
            <MailIcon aria-hidden="true" className="mb-2 size-5 text-primary" />
            <CardTitle>{t("emailLabel")}</CardTitle>
          </CardHeader>
          <CardContent>
            <a
              href={`mailto:${CONTACT_EMAIL}`}
              className="text-primary underline underline-offset-4"
            >
              {CONTACT_EMAIL}
            </a>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>{t("hinweisTitel")}</CardTitle>
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
