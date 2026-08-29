import { getSession } from "@/lib/session";
import { redirect } from "next/navigation";
import { isAdmin } from "@/lib/admin";
import { resolveUserSlug } from "@/lib/slug";

/** Legacy /dashboard → role-aware home: admins land on the agency console. */
export default async function DashboardRedirect({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const session = await getSession();
  const { locale } = await params;
  if (!session) redirect(`/${locale}/login`);
  if (isAdmin(session)) redirect(`/${locale}/admin`);
  redirect(`/${locale}/client/${await resolveUserSlug(session.user.id, session.user.email)}`);
}
