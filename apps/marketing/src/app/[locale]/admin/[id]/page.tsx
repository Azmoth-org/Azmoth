import { getSession } from "@/lib/session";
import prisma from "@/lib/prisma";
import { redirect } from "next/navigation";
import { isAdmin } from "@/lib/admin";
import { resolveUserSlug } from "@/lib/slug";

/** Legacy /admin/[id] → the project page now lives at /admin/projects/[id]. */
export default async function AdminProjectRedirect({
  params,
}: {
  params: Promise<{ locale: string; id: string }>;
}) {
  const session = await getSession();
  const { locale, id } = await params;
  if (!session) redirect(`/${locale}/login`);
  if (!isAdmin(session)) {
    redirect(`/${locale}/client/${await resolveUserSlug(session.user.id, session.user.email)}`);
  }
  redirect(`/${locale}/admin/projects/${id}`);
}
