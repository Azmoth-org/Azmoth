/**
 * A catalogue line in which `{email}` becomes a real `mailto:` link.
 *
 * The address is interpolated rather than typed into the German text so that the
 * Impressum, the privacy notice, the footer and the contact page cannot end up naming
 * three different mailboxes — `siteConfig.email` is the only one there is, and a visitor
 * who finds two concludes, correctly, that nobody reads either.
 *
 * Plain string splitting rather than `t.rich`: the catalogue entries are flat strings
 * consumed through `t.raw` (they arrive as arrays), so there is no message context to
 * hang a rich-text tag on.
 */
export function MailLine({ line, email }: { line: string; email: string }) {
  const [before, ...rest] = line.split("{email}");
  if (rest.length === 0) return <>{line}</>;

  return (
    <>
      {before}
      <a href={`mailto:${email}`} className="text-primary underline underline-offset-4">
        {email}
      </a>
      {rest.join("")}
    </>
  );
}
