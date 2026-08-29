import { getSession } from "@/lib/session";
import prisma from "@/lib/prisma";
import { redirect } from "next/navigation";
import { isAdmin } from "@/lib/admin";
import { resolveUserSlug } from "@/lib/slug";
import { getPipelineTemplate } from "@/lib/pipelines";
import { ProjectCard } from "@/components/portal/ProjectCard";
import { OpenChatButton } from "@/components/portal/OpenChatButton";

export default async function ClientPage({
  params,
}: {
  params: Promise<{ locale: string; slug: string }>;
}) {
  const session = await getSession();
  const { locale, slug } = await params;
  if (!session) redirect(`/${locale}/login`);

  const client = await prisma.user.findUnique({
    where: { slug },
    select: { id: true, name: true, email: true },
  });
  if (!client) redirect(`/${locale}/dashboard`);

  const isOwner = client.id === session.user.id;
  if (!isOwner && !isAdmin(session)) {
    redirect(`/${locale}/client/${await resolveUserSlug(session.user.id, session.user.email)}`);
  }

  const [projects, briefs] = await Promise.all([
    prisma.project.findMany({
      where: { userId: client.id },
      include: { stages: { orderBy: { order: "asc" } } },
      orderBy: { createdAt: "desc" },
    }),
    prisma.brief.findMany({
      where: { userId: client.id },
      orderBy: { createdAt: "desc" },
    }),
  ]);

  const activeProjects = projects.filter(
    (p) => p.status === "in_progress" || p.status === "approved" || p.status === "proposed"
  ).length;
  const completedProjects = projects.filter((p) => p.status === "completed").length;
  const pendingBriefs = briefs.filter((b) => b.status === "received").length;

  return (
    <div className="bg-[var(--background)]">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="mb-12">
          <h1 className="text-3xl font-bold tracking-[-0.03em] font-['Manrope',system-ui,sans-serif] text-foreground">
            Welcome, <span className="text-[var(--accent)]">{client.name || client.email.split("@")[0]}</span>
          </h1>
          <p className="text-[var(--muted)] mt-1 text-sm">{client.email}</p>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-12">
          {[
            { label: "Active Projects", value: activeProjects, color: "from-[var(--accent)]/20 to-[var(--accent)]/5" },
            { label: "Submitted Briefs", value: briefs.length, color: "from-emerald-500/20 to-emerald-500/5" },
            { label: "Completed", value: completedProjects, color: "from-amber-500/20 to-amber-500/5" },
          ].map((stat) => (
            <div
              key={stat.label}
              className={`bg-gradient-to-br ${stat.color} border border-[var(--border)] rounded-2xl p-6`}
            >
              <p className="text-3xl font-bold mb-1">{stat.value}</p>
              <p className="text-sm text-[var(--muted)]">{stat.label}</p>
            </div>
          ))}
        </div>

        {/* Projects with live pipeline */}
        <div className="mb-12">
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-xl font-semibold tracking-[-0.02em]">Your Projects</h2>
            <OpenChatButton className="px-4 py-2 bg-[var(--accent)] hover:opacity-90 text-sm font-medium rounded-xl transition-all btn-press">
              New Project
            </OpenChatButton>
          </div>

          {projects.length === 0 ? (
            <div className="bg-[var(--surface)] border border-[var(--border)] rounded-2xl p-12 text-center">
              <p className="text-[var(--muted)] text-lg mb-4">No projects yet</p>
              <OpenChatButton className="px-6 py-3 bg-[var(--accent)] hover:opacity-90 font-medium rounded-xl transition-all btn-press">
                Start Your First Project
              </OpenChatButton>
            </div>
          ) : (
            <div className="space-y-4">
              {projects.map((project) => (
                <ProjectCard
                  key={project.id}
                  project={project}
                  template={getPipelineTemplate(project.category)}
                  slug={slug}
                />
              ))}
            </div>
          )}
        </div>

        {/* Briefs awaiting promotion */}
        {pendingBriefs > 0 && (
          <div>
            <h2 className="text-xl font-semibold mb-6 tracking-[-0.02em]">Submitted Briefs</h2>
            <div className="space-y-3">
              {briefs
                .filter((b) => b.status === "received")
                .map((brief) => (
                  <div
                    key={brief.id}
                    className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-5 flex items-center justify-between"
                  >
                    <div className="flex-1">
                      <p className="font-medium mb-1">{brief.name || brief.category || "Brief"}</p>
                      <p className="text-sm text-[var(--muted)]">
                        {brief.category} &middot; {new Date(brief.createdAt).toLocaleDateString()}
                      </p>
                    </div>
                    <span className="px-3 py-1 text-xs rounded-full font-medium bg-white/10 text-[var(--muted)]">
                      awaiting review
                    </span>
                  </div>
                ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
