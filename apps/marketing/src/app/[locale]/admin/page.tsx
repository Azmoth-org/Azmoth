import { getSession } from "@/lib/session";
import prisma from "@/lib/prisma";
import { redirect } from "next/navigation";
import { isAdmin } from "@/lib/admin";
import { resolveUserSlug } from "@/lib/slug";
import { getPipelineTemplate } from "@/lib/pipelines";
import { AgencyConsole } from "@/components/agency/AgencyConsole";

export default async function AdminPage({
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

  const [briefs, projects] = await Promise.all([
    prisma.brief.findMany({
      orderBy: { createdAt: "desc" },
      take: 100,
    }),
    prisma.project.findMany({
      include: {
        stages: { orderBy: { order: "asc" } },
        brief: true,
        user: { select: { name: true, email: true, slug: true } },
      },
      orderBy: { updatedAt: "desc" },
      take: 100,
    }),
  ]);

  const briefsWithTemplate = briefs.map((b) => ({
    ...b,
    template: getPipelineTemplate(b.category),
  }));

  const awaitingReview = briefs.filter((b) => b.status === "received").length;
  const activeProjects = projects.filter(
    (p) => p.status === "in_progress" || p.status === "approved" || p.status === "proposed"
  ).length;

  return (
    <div className="bg-[var(--background)]">
      <div className="mx-auto max-w-7xl">
        {/* Compact header — the portal shell header already sits above */}
        <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-2xl md:text-3xl font-bold tracking-[-0.03em] font-['Manrope',system-ui,sans-serif] text-foreground">
              Agency Console
            </h1>
            <p className="text-sm text-muted-foreground mt-0.5">
              Every project at a glance. Drive statuses from here, dig into details on a project page.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span className="px-3 py-1 rounded-full text-xs font-medium bg-white/10 text-muted-foreground">
              {projects.length} projects
            </span>
            <span className="px-3 py-1 rounded-full text-xs font-medium bg-[var(--accent)]/15 text-[var(--accent)]">
              {activeProjects} active
            </span>
            <span className="px-3 py-1 rounded-full text-xs font-medium bg-amber-500/15 text-amber-400">
              {awaitingReview} awaiting review
            </span>
          </div>
        </div>

        <AgencyConsole briefs={briefsWithTemplate} projects={projects} />
      </div>
    </div>
  );
}
