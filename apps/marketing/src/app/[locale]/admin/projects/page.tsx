import { getSession } from "@/lib/session";
import prisma from "@/lib/prisma";
import { redirect } from "next/navigation";
import { isAdmin } from "@/lib/admin";
import { resolveUserSlug } from "@/lib/slug";
import { ProjectsList } from "@/components/agency/ProjectsList";

export default async function AdminProjectsPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const session = await getSession();
  const { locale } = await params;
  if (!session) redirect(`/${locale}/login`);
  if (!isAdmin(session)) {
    redirect(`/${locale}/client/${await resolveUserSlug(session.user.id, session.user.email)}`);
  }

  const projects = await prisma.project.findMany({
    include: {
      stages: { orderBy: { order: "asc" } },
      brief: true,
      user: { select: { name: true, email: true, slug: true } },
    },
    orderBy: { updatedAt: "desc" },
    take: 200,
  });

  const active = projects.filter(
    (p) => p.phase !== "completed" && p.status !== "completed"
  ).length;

  return (
    <div className="bg-[var(--background)]">
      <div className="mx-auto max-w-7xl">
        <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-2xl md:text-3xl font-bold tracking-[-0.03em] font-['Manrope',system-ui,sans-serif] text-foreground">
              Projects
            </h1>
            <p className="text-sm text-muted-foreground mt-0.5">
              Every project in the pipeline — open one to drive its kanban, stages and billing.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span className="px-3 py-1 rounded-full text-xs font-medium bg-white/10 text-muted-foreground">
              {projects.length} total
            </span>
            <span className="px-3 py-1 rounded-full text-xs font-medium bg-[var(--accent)]/15 text-[var(--accent)]">
              {active} active
            </span>
          </div>
        </div>

        <ProjectsList projects={projects} />
      </div>
    </div>
  );
}
