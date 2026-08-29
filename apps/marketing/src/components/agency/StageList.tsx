"use client";

import { useState } from "react";

export type StageItem = {
  id: string;
  key: string;
  title: string | null;
  order: number;
  status: string;
  startedAt: string | Date | null;
  completedAt: string | Date | null;
};

export const STAGE_STATUSES = ["pending", "in_progress", "review", "done", "blocked"];

export const STAGE_COLORS: Record<string, string> = {
  done: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
  in_progress: "bg-[var(--accent)]/15 text-[var(--accent)] border-[var(--accent)]/30",
  review: "bg-amber-500/15 text-amber-400 border-amber-500/30",
  blocked: "bg-red-500/15 text-red-400 border-red-500/30",
  pending: "bg-white/5 text-[var(--muted)] border-[var(--border)]",
};

/**
 * Shared stage manager — status buttons, delete, add custom stage.
 * Used by the agency console's expanded table row and the admin project page.
 */
export function StageList({
  stages,
  projectId,
  busyId,
  onSetStatus,
  onDelete,
  onAdd,
}: {
  stages: StageItem[];
  projectId: string;
  busyId: string | null;
  onSetStatus: (stageId: string, status: string) => void;
  onDelete: (stageId: string) => void;
  onAdd: (projectId: string, title: string) => void;
}) {
  const [adding, setAdding] = useState(false);
  const [title, setTitle] = useState("");

  return (
    <div>
      <div className="divide-y divide-[var(--border)]">
        {stages.map((stage) => (
          <div key={stage.id} className="px-5 py-3 flex items-center gap-3">
            <div className="flex-1 min-w-0">
              <p className="text-[14px] text-foreground tracking-[-0.01em]">{stage.title}</p>
              <p className="text-[11px] text-[var(--muted)] tracking-[-0.01em]">
                {stage.completedAt
                  ? `Done ${new Date(stage.completedAt).toLocaleDateString()}`
                  : stage.startedAt
                    ? `Started ${new Date(stage.startedAt).toLocaleDateString()}`
                    : "Not started"}
              </p>
            </div>
            <div className="flex items-center gap-1.5">
              {STAGE_STATUSES.map((st) => (
                <button
                  key={st}
                  type="button"
                  disabled={busyId === stage.id}
                  onClick={() => onSetStatus(stage.id, st)}
                  className={`px-2 py-1 rounded-md text-[11px] font-medium border transition-all btn-press disabled:opacity-40 ${
                    stage.status === st
                      ? STAGE_COLORS[st]
                      : "bg-transparent border-transparent text-[var(--muted)]/50 hover:text-[var(--muted)]"
                  }`}
                >
                  {st.replace("_", " ")}
                </button>
              ))}
              <button
                type="button"
                disabled={busyId === stage.id}
                onClick={() => onDelete(stage.id)}
                className="px-2 py-1 rounded-md text-[11px] text-red-400/60 hover:text-red-400 transition-colors btn-press disabled:opacity-40"
                title="Remove stage"
              >
                ✕
              </button>
            </div>
          </div>
        ))}
      </div>
      <div className="px-5 py-3 border-t border-[var(--border)] bg-[var(--background)]/40">
        {adding ? (
          <form
            className="flex items-center gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              if (!title.trim()) return;
              onAdd(projectId, title);
              setTitle("");
              setAdding(false);
            }}
          >
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Stage title (e.g. Content Migration)"
              className="flex-1 px-3 py-2 bg-[var(--surface)] border border-[var(--border)] rounded-[10px] text-[13px] text-foreground focus:outline-none focus:border-[var(--accent)] placeholder:text-[var(--muted)]/50"
              autoFocus
            />
            <button type="submit" className="px-3 py-2 bg-[var(--accent)] text-white rounded-[10px] text-[13px] font-medium btn-press">
              Add
            </button>
            <button
              type="button"
              onClick={() => setAdding(false)}
              className="px-3 py-2 text-[13px] text-[var(--muted)] btn-press"
            >
              Cancel
            </button>
          </form>
        ) : (
          <button
            type="button"
            onClick={() => setAdding(true)}
            className="text-[12px] text-[var(--accent)] hover:opacity-80 transition-opacity tracking-[-0.01em]"
          >
            + Add custom stage
          </button>
        )}
      </div>
    </div>
  );
}
