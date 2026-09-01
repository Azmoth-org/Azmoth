import Link from "next/link";

/**
 * The 404, written rather than imported.
 *
 * Fumadocs exports a `DefaultNotFound`, and it says "Page Not Found" in English. Every other
 * string on this site is German, and the one page a reader reaches by mistake is a poor place to
 * switch languages. It deliberately does not carry the documentation shell: the sidebar's job is
 * to show where you are inside the tree, and the answer here is "nowhere".
 */
export default function NotFound() {
  return (
    <main className="flex flex-1 flex-col items-center justify-center gap-4 px-6 py-24 text-center">
      <p className="text-sm font-medium text-fd-muted-foreground">404</p>
      <h1 className="azm-display text-[2rem] text-balance sm:text-[2.5rem]">
        Diese Seite gibt es nicht
      </h1>
      <p className="max-w-md leading-relaxed text-fd-muted-foreground">
        Der Link ist veraltet oder die Seite wurde umbenannt. Der Einstieg in die Dokumentation
        liegt auf der Startseite.
      </p>
      <Link
        href="/"
        className="mt-2 inline-flex h-10 items-center rounded-full bg-fd-primary px-5 text-sm font-medium text-fd-primary-foreground transition-opacity hover:opacity-90"
      >
        Zur Dokumentation
      </Link>
    </main>
  );
}
