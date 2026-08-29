import { getSession } from "@/lib/session";
import { redirect } from "next/navigation";
import { resolveUserSlug } from "@/lib/slug";

/** Legacy /dashboard/[id] → the same project under /client/{slug}/[id]. */
export default async function DashboardProjectRedirect({
  params,
}: {
  params: Promise<{ locale: string; id: string }>;
}) {
  const session = await getSession();
  const { locale, id } = await params;
  if (!session) redirect(`/${locale}/login`);
  redirect(`/${locale}/client/${await resolveUserSlug(session.user.id, session.user.email)}/${id}`);
}
