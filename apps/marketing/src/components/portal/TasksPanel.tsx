"use client";

import { useEffect, useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";

type Task = { id: string; title: string; status: "pending" | "done"; order: number };

/** Planner tasks: add, toggle, delete — shadcn primitives, backed by the tasks API. */
export default function TasksPanel({ projectId }: { projectId: string }) {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    fetch(`/api/projects/${projectId}/tasks`, { cache: "no-store" })
      .then((r) => r.json())
      .then((d) => setTasks(d.tasks ?? []))
      .catch(() => {});
  }, [projectId]);

  const add = async () => {
    const t = title.trim();
    if (!t || busy) return;
    setBusy(true);
    try {
      const res = await fetch(`/api/projects/${projectId}/tasks`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: t }),
      });
      const d = await res.json();
      if (d.task) setTasks((list) => [...list, d.task]);
      setTitle("");
    } finally {
      setBusy(false);
    }
  };

  const toggle = async (task: Task, done: boolean) => {
    const next = done ? "done" : "pending";
    setTasks((list) => list.map((x) => (x.id === task.id ? { ...x, status: next } : x)));
    await fetch(`/api/tasks/${task.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: next }),
    });
  };

  const remove = async (task: Task) => {
    setTasks((list) => list.filter((x) => x.id !== task.id));
    await fetch(`/api/tasks/${task.id}`, { method: "DELETE" });
  };

  const done = tasks.filter((t) => t.status === "done").length;

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h3 className="text-lg font-semibold tracking-[-0.01em]">Tasks</h3>
        <span className="text-xs text-muted-foreground">
          {done}/{tasks.length} done
        </span>
      </div>

      <div className="mb-4 flex gap-2">
        <Input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && add()}
          placeholder="Add a task — e.g. share the content outline"
          className="flex-1"
        />
        <Button type="button" onClick={add} disabled={busy || !title.trim()}>
          <Plus className="size-4" />
          Add
        </Button>
      </div>

      {tasks.length === 0 ? (
        <p className="rounded-xl border border-dashed border-[var(--border)] py-8 text-center text-sm text-muted-foreground">
          No tasks yet — add the first one, or ask your rep in the chat tab.
        </p>
      ) : (
        <ul className="space-y-2">
          {tasks.map((task) => (
            <li
              key={task.id}
              className="flex items-center gap-3 rounded-xl border border-[var(--border)] bg-[var(--surface)] px-4 py-3"
            >
              <Checkbox
                id={`task-${task.id}`}
                checked={task.status === "done"}
                onCheckedChange={(v) => toggle(task, v === true)}
                className="h-11 w-11 rounded-full"
              />
              <label
                htmlFor={`task-${task.id}`}
                className={`flex-1 cursor-pointer text-sm transition-colors ${
                  task.status === "done"
                    ? "text-muted-foreground line-through"
                    : "text-foreground"
                }`}
              >
                {task.title}
              </label>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                onClick={() => remove(task)}
                aria-label="Delete task"
              >
                <Trash2 className="size-4" />
              </Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
