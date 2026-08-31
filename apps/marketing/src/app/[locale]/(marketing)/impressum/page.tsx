import type { Metadata } from "next";
import { useTranslations } from "next-intl";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { PlaceholderNotice } from "@/components/placeholder-notice";
import { Section, SectionHeading } from "@/components/section";
import { hasPlaceholder } from "@/lib/legal";
import { buildPageMetadata } from "@/lib/seo";
import { siteConfig } from "@/lib/site";
import { MailLine } from "@/components/mail-line";

/**
 * Anbieterkennzeichnung — the page German law requires and does not treat as optional.
 *
 * It ships with placeholders, a visible draft banner and `noindex` for exactly as long as
 * those placeholders survive; see `lib/legal.ts` for why that is the shape rather than a
 * `TODO` comment somebody has to notice.
 */
type Abschnitt = { titel: string; zeilen: string[] };

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "metadaten" });
  const tPage = await getTranslations({ locale, namespace: "impressum" });

  return {
    ...buildPageMetadata({
      path: "/impressum",
      title: t("impressumTitel"),
      description: t("impressumBeschreibung"),
    }),
    /*
      `follow` stays on: the page links to Datenschutz and to the contact page, and there
      is no reason to strand those. It is only this page's own content that should not be
      indexed while it is a draft.
    */
    ...(hasPlaceholder(tPage.raw("abschnitte"))
      ? { robots: { index: false, follow: true } }
      : {}),
  };
}

export default async function ImpressumPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  return <ImpressumContent />;
}

function ImpressumContent() {
  const t = useTranslations("impressum");
  const abschnitte = t.raw("abschnitte") as Abschnitt[];

  return (
    <Section className="pt-16 lg:pt-24">
      <SectionHeading title={t("titel")} subtitle={t("untertitel")} align="start" as="h1" />

      {hasPlaceholder(abschnitte) ? (
        <PlaceholderNotice className="mt-8 max-w-3xl" text={t("platzhalterHinweis")} />
      ) : null}

      <div className="mt-10 flex max-w-3xl flex-col gap-8">
        {abschnitte.map((abschnitt) => (
          <section key={abschnitt.titel}>
            <h2 className="text-base font-medium">{abschnitt.titel}</h2>
            <div className="mt-2 flex flex-col gap-1.5 leading-relaxed text-muted-foreground">
              {abschnitt.zeilen.map((zeile) => (
                <p key={zeile}>
                  <MailLine line={zeile} email={siteConfig.email} />
                </p>
              ))}
            </div>
          </section>
        ))}
      </div>
    </Section>
  );
}
