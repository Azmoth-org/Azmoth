"use client";

import { useEffect, useMemo, useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import {
  Kanban,
  KanbanColumn,
  KanbanColumnContent,
  KanbanItem,
  KanbanItemHandle,
  KanbanOverlay,
  type KanbanCommitMeta,
} from "@/components/reui/kanban";
import { api } from "@/lib/fetchApi";

export type KanbanTask = {
  id: string;
  title: string;
  status: string; // pending | in_progress | review | done
};

export const TASK_COLUMNS = [
  { key: "pending", title: "To do" },
  { key: "in_progress", title: "In progress" },
  { key: "review", title: "Review" },
  { key: "done", title: "Done" },
] as const;

const COLUMN_ACCENTS: Record<string, string> = {
  pending: "bg-[var(--muted)]/50",
  in_progress: "bg-[var(--accent)]",
  review: "bg-amber-400",
  done: "bg-emerald-400",
};

/**
 * Per-project task kanban (ReUI Kanban, @dnd-kit): To do → In progress →
 * Review → Done. Moves PATCH /api/tasks/[id] {status} with optimistic UI +
 * Sonner rollback; add/delete wired to the project tasks API.
 */
export function TasksKanban({
  projectId,
  tasks,
}: {
  projectId: string;
  tasks: KanbanTask[];
}) {
  const initial = useMemo<Record<string, KanbanTask[]>>(() => {
    const cols: Record<string, KanbanTask[]> = {};
    for (const col of TASK_COLUMNS) {
      cols[col.key] = tasks.filter((t) => t.status === col.key);
    }
    return cols;
  }, [tasks]);

  const [columns, setColumns] = useState(initial);
  useEffect(() => {
    setColumns(initial);
  }, [initial]);

  const [busy, setBusy] = useState<string | null>(null);
  const [newTitle, setNewTitle] = useState("");

  const commit = async (
    value: Record<string, KanbanTask[]>,
    meta: KanbanCommitMeta<KanbanTask>
  ) => {
    if (meta.kind !== "item") return;
    if (meta.activeContainer === meta.overContainer) return;

    const id = String(meta.event.active.id);
    // The target column key IS the new status — the moved task object keeps
    // its old status field (only the column array membership changed).
    const status = meta.overContainer;
    const task = (value[meta.overContainer] ?? []).find((t) => t.id === id);
    if (!task) return;

    setBusy(id);
    try {
      await api(`/api/tasks/${id}`, "PATCH", { status });
      toast.success(`Moved to ${TASK_COLUMNS.find((c) => c.key === status)?.title ?? status}.`);
    } catch {
      setColumns(meta.previousValue);
      toast.error("Couldn't move the task — reverted.");
    } finally {
      setBusy(null);
    }
  };

  const addTask = async () => {
    const title = newTitle.trim();
    if (!title) return;
    setBusy("new");
    try {
      const res = await api(`/api/projects/${projectId}/tasks`, "POST", { title });
      const task = res.task as KanbanTask;
      setColumns((cols) => ({ ...cols, pending: [...cols.pending, task] }));
      setNewTitle("");
      toast.success("Task added.");
    } catch {
      toast.error("Couldn't add the task.");
    } finally {
      setBusy(null);
    }
  };

  const deleteTask = async (id: string) => {
    setBusy(id);
    try {
      await api(`/api/tasks/${id}`, "DELETE");
      setColumns((cols) => {
        const next: Record<string, KanbanTask[]> = {};
        for (const col of TASK_COLUMNS) {
          next[col.key] = cols[col.key].filter((t) => t.id !== id);
        }
        return next;
      });
    } catch {
      toast.error("Couldn't delete the task.");
    } finally {
      setBusy(null);
    }
  };

  const renderCard = (task: KanbanTask) => (
    <div className="flex items-start gap-2 p-3">
      <p className="min-w-0 flex-1 text-[13px] font-medium leading-snug text-foreground">
        {task.title}
      </p>
      <button
        type="button"
        disabled={busy === task.id}
        onClick={(e) => {
          e.stopPropagation();
          deleteTask(task.id);
        }}
        title="Delete task"
        className="shrink-0 rounded-md p-1 text-muted-foreground/60 transition-colors hover:bg-foreground/5 hover:text-red-400 disabled:opacity-40"
      >
        <Trash2 className="size-3.5" />
      </button>
    </div>
  );

  return (
    <div>
      {/* Add task */}
      <form
        className="mb-3 flex items-center gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          addTask();
        }}
      >
        <input
          type="text"
          value={newTitle}
          onChange={(e) => setNewTitle(e.target.value)}
          placeholder="Add a task…"
          className="h-9 flex-1 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 text-[13px] text-foreground outline-none transition-colors placeholder:text-[var(--muted)]/50 focus:border-[var(--accent)]"
        />
        <button
          type="submit"
          disabled={busy === "new" || !newTitle.trim()}
          className="flex h-9 items-center gap-1 rounded-lg bg-[var(--accent)] px-3 text-[13px] font-medium text-white transition-all btn-press hover:opacity-90 disabled:opacity-40"
        >
          <Plus className="size-4" />
          Add
        </button>
      </form>

      <Kanban
        value={columns}
        onValueChange={setColumns}
        getItemValue={(t) => t.id}
        onValueCommit={commit}
        restoreOnCancel
      >
        <div className="flex gap-3">
          {TASK_COLUMNS.map((col) => {
            const items = columns[col.key] ?? [];
            return (
              <KanbanColumn
                key={col.key}
                value={col.key}
                className="w-64 shrink-0 rounded-xl border border-[var(--border)] bg-[var(--surface)]/60"
              >
                <div className="flex items-center justify-between border-b border-[var(--border)] px-3 py-2.5">
                  <div className="flex items-center gap-2">
                    <span className={`h-2 w-2 rounded-full ${COLUMN_ACCENTS[col.key]}`} />
                    <p className="text-[13px] font-semibold tracking-[-0.01em] text-foreground">
                      {col.title}
                    </p>
                  </div>
                  <span className="rounded-full bg-foreground/5 px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
                    {items.length}
                  </span>
                </div>

                <KanbanColumnContent value={col.key} className="min-h-20 gap-2 p-2">
                  {items.map((task) => (
                    <KanbanItem key={task.id} value={task.id}>
                      <KanbanItemHandle className="cursor-grab rounded-lg border border-[var(--border)] bg-card shadow-sm transition-colors hover:border-[var(--accent)]/40 active:cursor-grabbing">
                        {renderCard(task)}
                      </KanbanItemHandle>
                    </KanbanItem>
                  ))}
                  {items.length === 0 && (
                    <p className="py-5 text-center text-[11px] text-muted-foreground/40">—</p>
                  )}
                </KanbanColumnContent>
              </KanbanColumn>
            );
          })}
        </div>

        <KanbanOverlay>
          {({ value }) => {
            const task = Object.values(columns).flat().find((t) => t.id === String(value));
            if (!task) return null;
            return (
              <div className="rounded-lg border border-[var(--border)] bg-card shadow-lg">
                {renderCard(task)}
              </div>
            );
          }}
        </KanbanOverlay>
      </Kanban>
    </div>
  );
}
