import { useTranslations } from "next-intl";
import { TriangleAlertIcon } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@workspace/ui/components/alert";

import { Section } from "@/components/section";
import type { LegalDocument } from "@/data/legal";

/**
 * Renders one legal document, with the draft warning it currently has to carry.
 *
 * The banner is not decoration: these texts still contain `[...]` placeholders where
 * company facts belong, and shipping them silently would put an unreviewed privacy
 * notice in front of real visitors. Delete the `<Alert>` when a lawyer has signed
 * the text off — not before.
 */
export function LegalDocumentView({ document }: { document: LegalDocument }) {
  const t = useTranslations("recht");
  const updated = new Intl.DateTimeFormat("de-DE", { dateStyle: "long" }).format(
    new Date(document.updated)
  );

  return (
    <Section className="pt-16 lg:pt-24">
      <div className="mx-auto max-w-3xl">
        <h1 className="font-heading text-3xl font-semibold tracking-tight sm:text-4xl">
          {document.title}
        </h1>
        <p className="mt-4 text-pretty text-muted-foreground">{document.intro}</p>
        <p className="mt-2 text-sm text-muted-foreground">Stand: {updated}</p>

        <Alert variant="destructive" className="mt-8">
          <TriangleAlertIcon />
          <AlertTitle>{t("platzhalterTitel")}</AlertTitle>
          <AlertDescription>{t("platzhalterText")}</AlertDescription>
        </Alert>

        <div className="mt-12 flex flex-col gap-10">
          {document.sections.map((section) => (
            <section key={section.title}>
              <h2 className="font-heading text-lg font-medium">{section.title}</h2>
              <div className="mt-3 flex flex-col gap-3">
                {section.body.map((paragraph) => (
                  <p
                    key={paragraph}
                    className="whitespace-pre-line text-pretty text-sm text-muted-foreground"
                  >
                    {paragraph}
                  </p>
                ))}
              </div>
            </section>
          ))}
        </div>
      </div>
    </Section>
  );
}
