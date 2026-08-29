import { getSession } from "@/lib/session";
import prisma from "@/lib/prisma";
import { redirect } from "next/navigation";
import { isAdmin } from "@/lib/admin";
import { resolveUserSlug } from "@/lib/slug";
import { AdminProjectDetail } from "@/components/agency/AdminProjectDetail";

export default async function AdminProjectPage({
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

  const project = await prisma.project.findUnique({
    where: { id },
    include: {
      stages: { orderBy: { order: "asc" } },
      brief: true,
      user: { select: { name: true, email: true, slug: true } },
      tasks: { orderBy: { order: "asc" } },
      payments: { orderBy: { createdAt: "desc" } },
    },
  });

  if (!project) redirect(`/${locale}/admin`);

  return <AdminProjectDetail project={project} />;
}
