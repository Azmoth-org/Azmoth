"use client";

import { useLocale } from "next-intl";
import { ArrowLeft, CheckCircle2, ExternalLink, Wallet } from "lucide-react";
import { Link } from "@/i18n/navigation";
import { phaseLabel, PROJECT_PHASES } from "@/lib/projectLifecycle";
import { StageList, type StageItem } from "@/components/agency/StageList";
import { TasksKanban, type KanbanTask } from "@/components/agency/TasksKanban";
import { useAdminProjectActions } from "@/components/agency/useAdminProjectActions";
import { Button } from "@/components/ui/button";

type Brief = {
  id: string;
  name: string | null;
  email: string | null;
  category: string | null;
  description: string | null;
  scope: string | null;
  status: string;
  createdAt: string | Date;
};

type Task = { id: string; title: string; status: string; order: number };

type Payment = {
  id: string;
  kind: string;
  amount: number;
  currency: string;
  status: string;
  createdAt: string | Date;
};

export type AdminProject = {
  id: string;
  name: string | null;
  category: string | null;
  status: string;
  phase: string;
  quote: unknown;
  paymentStatus: string | null;
  createdAt: string | Date;
  updatedAt: string | Date;
  brief: Brief | null;
  user: { name: string | null; email: string | null; slug: string | null } | null;
  stages: StageItem[];
  tasks: Task[];
  payments: Payment[];
};

type QuoteShape = {
  total?: number;
  currency?: string;
  depositPercent?: number;
  depositAmount?: number;
};

/** Defensive parse of the Json quote field — never trust JsonValue shape. */
function parseQuote(quote: unknown): QuoteShape | null {
  if (typeof quote !== "object" || quote === null) return null;
  const obj = quote as Record<string, unknown>;
  return {
    total: typeof obj.total === "number" ? obj.total : undefined,
    currency: typeof obj.currency === "string" ? obj.currency : undefined,
    depositPercent: typeof obj.depositPercent === "number" ? obj.depositPercent : undefined,
    depositAmount: typeof obj.depositAmount === "number" ? obj.depositAmount : undefined,
  };
}

const PROJECT_STATUSES = ["proposed", "approved", "in_progress", "launched", "completed"];

const PROJECT_COLORS: Record<string, string> = {
  proposed: "bg-white/10 text-[var(--muted)]",
  approved: "bg-emerald-500/20 text-emerald-400",
  in_progress: "bg-[var(--accent)]/20 text-[var(--accent)]",
  launched: "bg-sky-500/20 text-sky-400",
  completed: "bg-emerald-500/20 text-emerald-400",
};

const PAYMENT_COLORS: Record<string, string> = {
  paid: "bg-emerald-500/15 text-emerald-400",
  pending: "bg-amber-500/15 text-amber-400",
  failed: "bg-red-500/15 text-red-400",
};

export function AdminProjectDetail({ project }: { project: AdminProject }) {
  const locale = useLocale();
  const { error, busyId, setProject, setPhase, setStage, addStage, deleteStage } =
    useAdminProjectActions();

  const doneCount = project.stages.filter((s) => s.status === "done").length;
  const progress = project.stages.length ? Math.round((doneCount / project.stages.length) * 100) : 0;
  const quote = parseQuote(project.quote);
  const doneTasks = project.tasks.filter((t) => t.status === "done").length;

  return (
    <div className="bg-[var(--background)]">
      <div className="mx-auto max-w-6xl">
        <Button asChild variant="ghost" className="mb-6 px-0 text-sm text-muted-foreground">
          <Link href="/admin/projects">
            <ArrowLeft className="size-4" />
            Projects
          </Link>
        </Button>

        {error && (
          <div className="mb-6 px-4 py-3 rounded-[12px] bg-red-500/10 border border-red-500/30 text-[13px] text-red-300">
            {error}
          </div>
        )}

        {/* Header */}
        <div className="mb-8 flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="mb-2 flex flex-wrap items-center gap-2">
              {project.category && (
                <span className="rounded-full bg-[var(--accent)]/10 px-3 py-1 text-xs font-medium text-[var(--accent)]">
                  {project.category}
                </span>
              )}
              <span className="rounded-full border border-[var(--border)] px-3 py-1 text-xs capitalize text-muted-foreground">
                {phaseLabel(project.phase, locale)}
              </span>
            </div>
            <h1 className="text-3xl md:text-4xl font-bold tracking-[-0.03em] text-foreground">
              {project.name ?? "Untitled project"}
            </h1>
            <p className="mt-2 text-sm text-muted-foreground">
              {project.user?.name || project.user?.email || "No client"} · created{" "}
              {new Date(project.createdAt).toLocaleDateString()}
            </p>
          </div>

          <div className="flex flex-col items-end gap-3">
            <div className="flex items-center gap-2">
              <select
                value={project.phase}
                disabled={busyId === project.id}
                onChange={(e) => setPhase(project.id, e.target.value)}
                title="Lifecycle phase"
                className="cursor-pointer rounded-[10px] border border-[var(--border)] bg-[var(--background)] px-3 py-1.5 text-[13px] font-medium text-muted-foreground outline-none transition-colors hover:text-foreground"
              >
                {PROJECT_PHASES.map((p) => (
                  <option key={p} value={p} className="text-foreground bg-[var(--surface)]">
                    {phaseLabel(p, locale)}
                  </option>
                ))}
              </select>
              <select
                value={project.status}
                disabled={busyId === project.id}
                onChange={(e) => setProject(project.id, e.target.value)}
                className={`cursor-pointer rounded-[10px] border px-3 py-1.5 text-[13px] font-medium outline-none bg-[var(--background)] ${
                  PROJECT_COLORS[project.status] ?? PROJECT_COLORS.proposed
                }`}
              >
                {PROJECT_STATUSES.map((s) => (
                  <option key={s} value={s} className="text-foreground bg-[var(--surface)]">
                    {s.replace("_", " ")}
                  </option>
                ))}
              </select>
            </div>
            {project.user?.slug && (
              <Link
                href={`/client/${project.user.slug}/${project.id}`}
                className="flex items-center gap-1.5 text-xs text-muted-foreground transition-colors hover:text-[var(--accent)]"
              >
                <ExternalLink className="size-3.5" />
                View client portal
              </Link>
            )}
          </div>
        </div>

        {/* Stats row */}
        <div className="mb-8 grid grid-cols-1 gap-4 sm:grid-cols-3">
          <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5">
            <div className="mb-1.5 flex justify-between text-xs text-muted-foreground">
              <span>Pipeline</span>
              <span>{progress}%</span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-[var(--border)]">
              <div className="h-full rounded-full bg-[var(--accent)]" style={{ width: `${progress}%` }} />
            </div>
            <p className="mt-2 text-xs text-muted-foreground">
              {doneCount}/{project.stages.length} stages
            </p>
          </div>
          <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5">
            <p className="text-xs text-muted-foreground mb-1.5">Tasks</p>
            <p className="flex items-center gap-1.5 text-sm font-medium text-foreground">
              <CheckCircle2 className="size-4 text-emerald-400" />
              {doneTasks}/{project.tasks.length} done
            </p>
          </div>
          <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5">
            <p className="text-xs text-muted-foreground mb-1.5">Payments</p>
            {quote?.total !== undefined ? (
              <p className="text-sm font-medium text-foreground">
                <Wallet className="mr-1 inline size-4 text-[var(--accent)]" />
                {quote.total.toLocaleString()} {quote.currency ?? "TND"}
                {project.paymentStatus ? ` · ${project.paymentStatus}` : ""}
              </p>
            ) : (
              <p className="text-sm text-muted-foreground">No quote yet</p>
            )}
          </div>
        </div>

        <div className="grid gap-6 lg:grid-cols-5">
          {/* Brief */}
          <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-6 lg:col-span-3">
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
              Brief
            </h2>
            <p className="text-[15px] leading-relaxed text-foreground/90">
              {project.brief?.description || "No brief description on file."}
            </p>
            {project.brief?.scope && (
              <p className="mt-4 text-sm text-muted-foreground">
                <span className="font-medium text-foreground">Scope:</span> {project.brief.scope}
              </p>
            )}
            {project.brief?.email && (
              <p className="mt-4 text-sm text-muted-foreground">
                <span className="font-medium text-foreground">Contact:</span>{" "}
                {project.brief.name ? `${project.brief.name} · ` : ""}
                {project.brief.email}
              </p>
            )}
          </div>

          {/* Payments history */}
          <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-6 lg:col-span-2">
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
              Payment history
            </h2>
            {project.payments.length === 0 ? (
              <p className="text-sm text-muted-foreground">No payments recorded.</p>
            ) : (
              <ul className="space-y-2.5">
                {project.payments.map((p) => (
                  <li key={p.id} className="flex items-center justify-between gap-2 text-sm">
                    <span className="capitalize text-foreground/90">
                      {p.kind.replace("_", " ")}
                      <span className="ml-2 text-xs text-muted-foreground">
                        {new Date(p.createdAt).toLocaleDateString()}
                      </span>
                    </span>
                    <span className="flex items-center gap-2">
                      <span className="font-medium text-foreground">
                        {p.amount.toLocaleString()} {p.currency}
                      </span>
                      <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${PAYMENT_COLORS[p.status] ?? "bg-white/10 text-muted-foreground"}`}>
                        {p.status}
                      </span>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        {/* Stages */}
        <div className="mt-6 overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface)]">
          <div className="border-b border-[var(--border)] px-5 py-4">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
              Pipeline
            </h2>
          </div>
          <StageList
            stages={project.stages}
            projectId={project.id}
            busyId={busyId}
            onSetStatus={setStage}
            onDelete={deleteStage}
            onAdd={addStage}
          />
        </div>

        {/* Tasks kanban */}
        <div className="mt-6 rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-6">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
              Tasks
            </h2>
            <span className="text-xs text-muted-foreground">
              {doneTasks}/{project.tasks.length} done
            </span>
          </div>
          <TasksKanban projectId={project.id} tasks={project.tasks} />
        </div>
      </div>
    </div>
  );
}
