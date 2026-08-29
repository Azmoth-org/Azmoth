import prisma from "@/lib/prisma";
import { slugify, slugFromEmail } from "@/lib/slugify";

export { slugify, slugFromEmail };

/** Unique slug for a NEW user: base from name or email local-part, then
 * -2/-3… suffix on collision. Used by the auth user-create hook so every
 * account gets a stable /client/{slug}. */
export async function generateUniqueSlug(
  email: string,
  name?: string | null
): Promise<string> {
  const base = slugify(name || "") || slugFromEmail(email);
  let slug = base;
  let i = 2;
  while (
    await prisma.user.findUnique({ where: { slug }, select: { id: true } })
  ) {
    slug = `${base}-${i++}`;
  }
  return slug;
}

/** Resolve a user's client-portal slug from the DB, falling back to the email-derived one. */
export async function resolveUserSlug(
  userId: string,
  email?: string | null
): Promise<string> {
  const user = await prisma.user.findUnique({
    where: { id: userId },
    select: { slug: true },
  });
  if (user?.slug) return user.slug;
  return slugFromEmail(email || "");
}
