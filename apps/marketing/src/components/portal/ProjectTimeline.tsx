"use client";

const STAGE_STATUS: Record<string, { label: string; cls: string; icon: string }> = {
  done: { label: "Done", cls: "bg-emerald-500/15 border-emerald-500/30 text-emerald-400", icon: "✓" },
  in_progress: { label: "In Progress", cls: "bg-[var(--accent)]/15 border-[var(--accent)]/30 text-[var(--accent)]", icon: "◐" },
  review: { label: "In Review", cls: "bg-amber-500/15 border-amber-500/30 text-amber-400", icon: "◔" },
  blocked: { label: "Blocked", cls: "bg-red-500/15 border-red-500/30 text-red-400", icon: "✕" },
  pending: { label: "Pending", cls: "bg-white/5 border-[var(--border)] text-[var(--muted)]", icon: "○" },
};

type Stage = {
  id: string;
  key: string;
  title: string | null;
  order: number;
  status: string;
  startedAt: string | Date | null;
  completedAt: string | Date | null;
};

type Brief = {
  id: string;
  name: string | null;
  email: string | null;
  category: string | null;
  description: string | null;
  scope: string | null;
  createdAt: string | Date;
} | null;

export function ProjectTimeline({
  project,
}: {
  project: {
    id: string;
    name: string | null;
    category: string | null;
    status: string;
    brief: Brief;
    stages: Stage[];
  };
}) {
  return (
    <div className="space-y-6">
      {/* Pipeline stages */}
      <div className="bg-[var(--surface)] border border-[var(--border)] rounded-2xl overflow-hidden">
        <div className="px-6 py-4 border-b border-[var(--border)] bg-[var(--surface)]/60">
          <h2 className="text-[16px] font-semibold text-foreground tracking-[-0.01em]">Delivery Pipeline</h2>
        </div>
        <div className="divide-y divide-[var(--border)]">
          {project.stages.map((stage, i) => {
            const st = STAGE_STATUS[stage.status] ?? STAGE_STATUS.pending;
            return (
              <div key={stage.id} className="flex items-center gap-4 px-6 py-4">
                <div className="flex flex-col items-center flex-shrink-0">
                  <div
                    className={`w-9 h-9 rounded-full border flex items-center justify-center text-[13px] font-bold ${
                      stage.status === "done"
                        ? "bg-emerald-500/15 border-emerald-500/40 text-emerald-400"
                        : stage.status === "in_progress"
                        ? "bg-[var(--accent)]/15 border-[var(--accent)]/40 text-[var(--accent)]"
                        : "bg-[var(--surface)] border-[var(--border)] text-[var(--muted)]"
                    }`}
                  >
                    {stage.status === "done" ? "✓" : i + 1}
                  </div>
                  {i < project.stages.length - 1 && (
                    <div className="w-px flex-1 min-h-[24px] bg-[var(--border)] my-1" />
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="font-medium text-[15px] text-foreground tracking-[-0.01em]">
                    {stage.title}
                  </p>
                  <p className="text-[12px] text-[var(--muted)] tracking-[-0.01em] mt-0.5">
                    {stage.completedAt
                      ? `Completed ${new Date(stage.completedAt).toLocaleDateString()}`
                      : stage.startedAt
                      ? `Started ${new Date(stage.startedAt).toLocaleDateString()}`
                      : "Not started"}
                  </p>
                </div>
                <span className={`px-3 py-1 text-[11px] rounded-full font-medium border flex-shrink-0 ${st.cls}`}>
                  {st.label}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Brief summary */}
      {project.brief && (
        <div className="bg-[var(--surface)] border border-[var(--border)] rounded-2xl p-6">
          <h2 className="text-[16px] font-semibold text-foreground tracking-[-0.01em] mb-4">Project Brief</h2>
          {project.brief.description && (
            <p className="text-[14px] text-[var(--muted)] leading-[1.6] tracking-[-0.01em] mb-4">
              {project.brief.description}
            </p>
          )}
          {project.brief.scope && (
            <div className="text-[13px] text-[var(--muted)] tracking-[-0.01em] space-y-1">
              {(() => {
                try {
                  const scope = JSON.parse(project.brief.scope);
                  return Object.entries(scope)
                    .filter(([, v]) => v && typeof v === "string")
                    .map(([k, v]) => (
                      <p key={k}>
                        <span className="text-foreground/60 capitalize">{k.replace(/_/g, " ")}:</span> {v as string}
                      </p>
                    ));
                } catch {
                  return <p>{project.brief.scope}</p>;
                }
              })()}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
