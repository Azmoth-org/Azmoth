import { useTranslations } from "next-intl";

import { Button } from "@workspace/ui/components/button";

import { Section } from "@/components/section";
import { Link } from "@/i18n/navigation";
import { routes } from "@/lib/site";

export default function NotFound() {
  const t = useTranslations("nichtGefunden");

  return (
    <Section className="py-28 lg:py-36">
      <div className="mx-auto flex max-w-md flex-col items-center gap-4 text-center">
        <p className="font-heading text-sm font-medium text-muted-foreground">404</p>
        <h1 className="font-heading text-3xl font-semibold tracking-tight sm:text-4xl">
          {t("titel")}
        </h1>
        <p className="text-muted-foreground">{t("text")}</p>
        <Button className="mt-2" render={<Link href={routes.home} />}>
          {t("cta")}
        </Button>
      </div>
    </Section>
  );
}
