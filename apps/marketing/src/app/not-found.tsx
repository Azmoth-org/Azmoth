import Link from "next/link";

/**
 * Root 404 — reached only for paths the locale middleware never matched (a request
 * for a file-like URL, say). It renders outside `[locale]`, so there is no
 * translation context here and the two strings are inline by necessity.
 */
export default function RootNotFound() {
  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="flex max-w-md flex-col items-center gap-4 text-center">
        <p className="font-heading text-sm font-medium text-muted-foreground">404</p>
        <h1 className="font-heading text-3xl font-semibold tracking-tight">
          Seite nicht gefunden
        </h1>
        <p className="text-muted-foreground">
          Diese Adresse gibt es nicht — oder nicht mehr.
        </p>
        <Link
          href="/"
          className="mt-2 inline-flex h-10 items-center rounded-4xl bg-primary px-4 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/80"
        >
          Zur Startseite
        </Link>
      </div>
    </div>
  );
}
