"use client";

import { Activity, Banknote, Inbox as InboxIcon } from "lucide-react";
import type { PipelineTemplate } from "@/lib/pipelines";
import { ProjectsTable, type AdminProjectRow } from "@/components/agency/ProjectsTable";
import { StageList, type StageItem } from "@/components/agency/StageList";
import { useAdminProjectActions } from "@/components/agency/useAdminProjectActions";

type Brief = {
  id: string;
  name: string | null;
  email: string | null;
  category: string | null;
  description: string | null;
  status: string;
  createdAt: string | Date;
  template?: PipelineTemplate;
};

type Project = {
  id: string;
  name: string | null;
  category: string | null;
  status: string;
  phase: string;
  quote: unknown;
  paymentStatus: string | null;
  createdAt: string | Date;
  stages: StageItem[];
  user: { name: string | null; email: string | null; slug: string | null } | null;
};

type QuoteShape = { total?: number };

/** Defensive parse of the Json quote field. */
function parseQuote(quote: unknown): QuoteShape | null {
  if (typeof quote !== "object" || quote === null) return null;
  const obj = quote as Record<string, unknown>;
  return { total: typeof obj.total === "number" ? obj.total : undefined };
}

/**
 * Agency console — the CEO overview: summary strip, projects list, briefs
 * inbox. Deep work (kanban, stages, billing) happens on the per-project page
 * (/admin/projects/[id]) and the customers section.
 */
export function AgencyConsole({ briefs, projects }: { briefs: Brief[]; projects: Project[] }) {
  const { error, busyId, promote, setProject, setStage, addStage, deleteStage } =
    useAdminProjectActions();

  // ── CEO stats ──
  const active = projects.filter(
    (p) => p.phase !== "completed" && p.status !== "completed"
  ).length;
  const pipelineValue = projects.reduce((sum, p) => sum + (parseQuote(p.quote)?.total ?? 0), 0);
  const outstandingPayments = projects.filter(
    (p) => p.phase !== "completed" && (p.paymentStatus === "partial" || p.paymentStatus === "unpaid")
  ).length;
  const blockedCount = projects.filter((p) =>
    p.stages.some((s) => s.status === "blocked")
  ).length;
  const needsAttention = briefs.filter((b) => b.status === "received").length + blockedCount;

  const stats = [
    { label: "Active projects", value: String(active), icon: Activity, color: "text-[var(--accent)]" },
    { label: "Pipeline value", value: pipelineValue ? `${pipelineValue.toLocaleString()} TND` : "—", icon: Banknote, color: "text-emerald-400" },
    { label: "Outstanding payments", value: String(outstandingPayments), icon: Banknote, color: "text-amber-400" },
    { label: "Needs attention", value: String(needsAttention), icon: InboxIcon, color: "text-red-400" },
  ];

  const projectRows: AdminProjectRow[] = projects.map((project) => {
    const doneCount = project.stages.filter((st) => st.status === "done").length;
    const pct = project.stages.length ? Math.round((doneCount / project.stages.length) * 100) : 0;
    return {
      id: project.id,
      name: project.name || project.category || project.id,
      category: project.category,
      clientEmail: project.user?.email ?? null,
      phase: project.phase,
      status: project.status,
      progress: pct,
      createdAt: project.createdAt.toString(),
      renderExpanded: () => (
        <StageList
          stages={project.stages}
          projectId={project.id}
          busyId={busyId}
          onSetStatus={setStage}
          onDelete={deleteStage}
          onAdd={addStage}
        />
      ),
    };
  });

  const received = briefs.filter((b) => b.status === "received").length;

  return (
    <div className="space-y-8">
      {error && (
        <div className="px-4 py-3 rounded-[12px] bg-red-500/10 border border-red-500/30 text-[13px] text-red-300">
          {error}
        </div>
      )}

      {/* ── CEO summary strip ── */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {stats.map((stat) => (
          <div key={stat.label} className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-4">
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <stat.icon className={`size-3.5 ${stat.color}`} />
              {stat.label}
            </div>
            <p className="mt-1.5 text-2xl font-bold tracking-[-0.02em] text-foreground">
              {stat.value}
            </p>
          </div>
        ))}
      </div>

      {/* ── Projects ── */}
      <section>
        <h2 className="text-lg font-semibold mb-3 tracking-[-0.02em] text-foreground">
          Projects <span className="text-muted-foreground text-sm font-normal">({projects.length})</span>
        </h2>
        {projects.length === 0 ? (
          <div className="bg-[var(--surface)] border border-[var(--border)] rounded-2xl p-10 text-center text-[var(--muted)]">
            No projects yet — start one from the Inbox below.
          </div>
        ) : (
          <ProjectsTable projects={projectRows} onStatusChange={setProject} />
        )}
      </section>

      {/* ── Inbox ── */}
      <section>
        <h2 className="text-lg font-semibold mb-3 tracking-[-0.02em] text-foreground">
          Inbox <span className="text-muted-foreground text-sm font-normal">({received})</span>
        </h2>
        {received === 0 ? (
          <div className="bg-[var(--surface)] border border-[var(--border)] rounded-2xl p-10 text-center text-[var(--muted)]">
            No briefs awaiting review
          </div>
        ) : (
          <div className="grid gap-3">
            {briefs
              .filter((b) => b.status === "received")
              .map((brief) => (
                <div key={brief.id} className="bg-[var(--surface)] border border-[var(--border)] rounded-2xl p-5">
                  <div className="flex items-start justify-between gap-4 mb-3">
                    <div>
                      <p className="font-medium text-foreground tracking-[-0.01em]">
                        {brief.name || "Anonymous"}{" "}
                        {brief.email && <span className="text-[var(--muted)] font-normal text-sm">· {brief.email}</span>}
                      </p>
                      <p className="text-[13px] text-[var(--muted)] tracking-[-0.01em] mt-0.5">
                        {brief.template?.label ?? brief.category} · {new Date(brief.createdAt).toLocaleString()}
                      </p>
                    </div>
                    <button
                      type="button"
                      disabled={busyId === brief.id}
                      onClick={() => promote(brief.id)}
                      className="px-4 py-1.5 bg-[var(--accent)] text-white rounded-[10px] text-[13px] font-medium hover:opacity-90 transition-all btn-press disabled:opacity-40"
                    >
                      {busyId === brief.id ? "Promoting…" : "Promote to project"}
                    </button>
                  </div>
                  {brief.description && (
                    <p className="text-[13px] text-[var(--muted)] leading-[1.6] tracking-[-0.01em] line-clamp-2">
                      {brief.description}
                    </p>
                  )}
                  <p className="text-[12px] text-[var(--muted)]/60 mt-3 tracking-[-0.01em]">
                    Pipeline: {brief.template?.stages.map((s) => s.title).join(" → ")}
                  </p>
                </div>
              ))}
          </div>
        )}
      </section>
    </div>
  );
}
