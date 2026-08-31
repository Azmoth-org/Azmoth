import type { Metadata } from "next";
import { useTranslations } from "next-intl";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { MailLine } from "@/components/mail-line";
import { PlaceholderNotice } from "@/components/placeholder-notice";
import { Section, SectionHeading } from "@/components/section";
import { hasPlaceholder } from "@/lib/legal";
import { buildPageMetadata } from "@/lib/seo";
import { siteConfig } from "@/lib/site";

/**
 * Datenschutzerklärung — a draft, and labelled as one.
 *
 * The substantive part is §7: in the pilot Azmoth processes only anonymised deliveries,
 * and the moment real billing data is involved the roles change — the practice becomes
 * controller, we become processor, and an Art. 28 agreement has to exist *before* the
 * first file moves. That is the paragraph a Datenschutzbeauftragter will read first, so
 * it says what the product actually enforces rather than what would be reassuring.
 *
 * Everything a lawyer has to supply is marked and, while it is marked, this page is
 * `noindex` and carries a visible banner. See `lib/legal.ts`.
 */
type Abschnitt = { titel: string; absaetze: string[] };

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "metadaten" });
  const tPage = await getTranslations({ locale, namespace: "datenschutz" });

  return {
    ...buildPageMetadata({
      path: "/datenschutz",
      title: t("datenschutzTitel"),
      description: t("datenschutzBeschreibung"),
    }),
    ...(hasPlaceholder(tPage.raw("abschnitte"))
      ? { robots: { index: false, follow: true } }
      : {}),
  };
}

export default async function DatenschutzPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  return <DatenschutzContent />;
}

function DatenschutzContent() {
  const t = useTranslations("datenschutz");
  const abschnitte = t.raw("abschnitte") as Abschnitt[];

  return (
    <Section className="pt-16 lg:pt-24">
      <SectionHeading title={t("titel")} subtitle={t("untertitel")} align="start" as="h1" />

      {hasPlaceholder(abschnitte) ? (
        <PlaceholderNotice className="mt-8 max-w-3xl" text={t("platzhalterHinweis")} />
      ) : null}

      <p className="mt-6 text-sm text-muted-foreground">{t("stand")}</p>

      <div className="mt-10 flex max-w-3xl flex-col gap-10">
        {abschnitte.map((abschnitt) => (
          <section key={abschnitt.titel}>
            <h2 className="text-base font-medium">{abschnitt.titel}</h2>
            <div className="mt-3 flex flex-col gap-3 leading-relaxed text-muted-foreground">
              {abschnitt.absaetze.map((absatz) => (
                <p key={absatz}>
                  <MailLine line={absatz} email={siteConfig.email} />
                </p>
              ))}
            </div>
          </section>
        ))}
      </div>
    </Section>
  );
}
