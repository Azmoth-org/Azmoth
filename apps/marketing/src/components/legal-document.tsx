import { useTranslations } from "next-intl";
import { TriangleAlertIcon } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@workspace/ui/components/alert";

import { Section } from "@/components/section";
import type { LegalDocument } from "@/data/legal";

/** `{{Firmenname}}` → a chip; everything else → text. Captures keep the split parts. */
const PLACEHOLDER = /\{\{([^}]+)\}\}/g;

/**
 * Renders one legal document, with the draft warnings it currently has to carry.
 *
 * Two of them, deliberately. The banner at the top says the whole text is
 * unreviewed; the chips below say exactly which words are missing. A `[...]` buried
 * mid-paragraph is the kind of thing that survives to production because nobody
 * scrolled — an amber chip reading "BITTE EINTRAGEN: USt-IdNr." does not.
 *
 * Delete both when a lawyer has signed the text off, not before. `data/legal.ts`
 * carries the full list of what has to be filled in first.
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
                    <ParagraphWithPlaceholders text={paragraph} />
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

function ParagraphWithPlaceholders({ text }: { text: string }) {
  // `split` with a capturing group interleaves the literal text and the captures,
  // so odd indices are the placeholder names and even indices the prose between.
  const parts = text.split(PLACEHOLDER);

  return (
    <>
      {parts.map((part, index) =>
        index % 2 === 1 ? (
          <strong
            key={`${part}-${index}`}
            data-placeholder
            className="mx-0.5 inline-block rounded-md bg-amber-100 px-1.5 py-0.5 align-baseline text-[0.8125rem] font-semibold text-amber-900 ring-1 ring-amber-300 dark:bg-amber-950 dark:text-amber-100 dark:ring-amber-800"
          >
            BITTE EINTRAGEN: {part}
          </strong>
        ) : (
          part
        )
      )}
    </>
  );
}
