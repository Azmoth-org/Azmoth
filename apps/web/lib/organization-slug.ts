/**
 * A URL-safe slug from an organisation's name.
 *
 * Better Auth requires one and enforces its uniqueness, so this only has to produce something legal
 * and recognisable. German names are the common case, which is why the umlauts are transliterated
 * rather than stripped: `NFD` alone would turn "Röntgenpraxis" into "Rontgenpraxis", and ö → oe is
 * what a German reader expects to see. The random suffix is what stops the second "Abrechnung
 * Müller" from colliding with the first and failing with an error nobody has a field to show.
 *
 * Shared by `components/auth/signup-form.tsx` (the organisation created at registration) and
 * `components/layout/organisation-switcher.tsx` (one created later from the rail) — both need the
 * exact same rule, or the same name would slug differently depending on which screen created it.
 */
export function slugifyOrganizationName(name: string): string {
  const base = name
    .toLowerCase()
    .replace(/ä/g, "ae")
    .replace(/ö/g, "oe")
    .replace(/ü/g, "ue")
    .replace(/ß/g, "ss")
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 40)

  const suffix = Math.random().toString(36).slice(2, 6)
  return base ? `${base}-${suffix}` : `organisation-${suffix}`
}
