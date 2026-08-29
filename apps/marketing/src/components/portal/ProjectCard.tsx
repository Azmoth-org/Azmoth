"use client";

import Link from "next/link";
import { useLocale } from "next-intl";
import type { PipelineTemplate } from "@/lib/pipelines";

type Stage = {
  id: string;
  key: string;
  title: string | null;
  order: number;
  status: string;
  startedAt: string | Date | null;
  completedAt: string | Date | null;
};

type Project = {
  id: string;
  name: string | null;
  category: string | null;
  status: string;
  createdAt: string | Date;
  stages: Stage[];
};

const STATUS_STYLES: Record<string, { dot: string; label: string }> = {
  done: { dot: "bg-emerald-400", label: "text-emerald-400" },
  in_progress: { dot: "bg-[var(--accent)] animate-pulse", label: "text-[var(--accent)]" },
  review: { dot: "bg-amber-400", label: "text-amber-400" },
  blocked: { dot: "bg-red-400", label: "text-red-400" },
  pending: { dot: "bg-white/20", label: "text-[var(--muted)]" },
};

const PROJECT_STATUS: Record<string, { label: string; cls: string }> = {
  proposed: { label: "Proposed", cls: "bg-white/10 text-[var(--muted)]" },
  approved: { label: "Approved", cls: "bg-emerald-500/20 text-emerald-400" },
  in_progress: { label: "In Progress", cls: "bg-[var(--accent)]/20 text-[var(--accent)]" },
  launched: { label: "Launched", cls: "bg-sky-500/20 text-sky-400" },
  completed: { label: "Completed", cls: "bg-emerald-500/20 text-emerald-400" },
};

export function ProjectCard({
  project,
  template,
  slug,
}: {
  project: Project;
  template: PipelineTemplate;
  slug: string;
}) {
  const locale = useLocale();
  const doneCount = project.stages.filter((s) => s.status === "done").length;
  const pct = project.stages.length
    ? Math.round((doneCount / project.stages.length) * 100)
    : 0;
  const status = PROJECT_STATUS[project.status] ?? PROJECT_STATUS.proposed;

  return (
    <Link
      href={`/${locale}/client/${slug}/${project.id}`}
      className="block bg-[var(--surface)] border border-[var(--border)] rounded-2xl p-6 hover:border-[var(--accent)]/40 transition-colors duration-150"
    >
      <div className="flex items-start justify-between gap-4 mb-5">
        <div>
          <h3 className="text-[17px] font-semibold text-foreground tracking-[-0.01em] mb-1">
            {project.name || project.category || "Project"}
          </h3>
          <p className="text-[13px] text-[var(--muted)] tracking-[-0.01em]">
            {template.label} &middot; {new Date(project.createdAt).toLocaleDateString()}
          </p>
        </div>
        <span className={`px-3 py-1 text-xs rounded-full font-medium ${status.cls}`}>
          {status.label}
        </span>
      </div>

      {/* Pipeline rail */}
      <div className="flex items-center gap-1.5 mb-4">
        {project.stages.map((stage, i) => {
          const st = STATUS_STYLES[stage.status] ?? STATUS_STYLES.pending;
          return (
            <div key={stage.id} className="flex items-center gap-1.5 flex-1">
              <div
                className={`h-1.5 flex-1 rounded-full transition-all duration-300 ${
                  stage.status === "done"
                    ? "bg-emerald-400"
                    : stage.status === "in_progress"
                    ? "bg-[var(--accent)]"
                    : stage.status === "review"
                    ? "bg-amber-400"
                    : stage.status === "blocked"
                    ? "bg-red-400"
                    : "bg-white/10"
                }`}
              />
              {i < project.stages.length - 1 && <div className="w-0.5" />}
            </div>
          );
        })}
      </div>

      {/* Stage dots + title */}
      <div className="flex items-center justify-between gap-2 mb-4">
        {project.stages.map((stage) => {
          const st = STATUS_STYLES[stage.status] ?? STATUS_STYLES.pending;
          return (
            <div key={stage.id} className="flex items-center gap-1.5 min-w-0">
              <span className={`w-2 h-2 rounded-full flex-shrink-0 ${st.dot}`} />
              <span className={`text-[11px] truncate tracking-[-0.01em] ${st.label}`}>
                {stage.title}
              </span>
            </div>
          );
        })}
      </div>

      <div className="flex items-center justify-between border-t border-[var(--border)] pt-4">
        <span className="text-[12px] text-[var(--muted)] tracking-[-0.01em]">
          {doneCount}/{project.stages.length} stages complete
        </span>
        <div className="flex items-center gap-3">
          <div className="w-28 h-1 rounded-full bg-white/10 overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-500"
              style={{ width: `${pct}%`, background: "linear-gradient(90deg, var(--accent), #5a52e0)" }}
            />
          </div>
          <span className="text-[12px] font-medium text-foreground">{pct}%</span>
        </div>
      </div>
    </Link>
  );
}
