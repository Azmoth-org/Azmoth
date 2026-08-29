/** Pure slug helpers — safe to import from client components (no prisma). */

/** Slugify any string to a URL-safe kebab slug. */
export function slugify(input: string): string {
  return input
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "") // strip diacritics
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 48);
}

/** Deterministic client-portal slug from an email (mirrors the migration backfill). */
export function slugFromEmail(email: string): string {
  return slugify(email.split("@")[0] || "") || "client";
}
