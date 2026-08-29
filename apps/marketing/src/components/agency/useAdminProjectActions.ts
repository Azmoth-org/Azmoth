"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/fetchApi";

/**
 * Shared admin project actions (status, phase, stages, brief promotion) with
 * busy/error state + router.refresh. Used by the console, the projects list
 * and the project detail page. Actions resolve true on success (optimistic
 * UIs roll back on false).
 */
export function useAdminProjectActions() {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const refresh = () => startTransition(() => router.refresh());

  async function run(action: () => Promise<unknown>, id: string): Promise<boolean> {
    setBusyId(id);
    setError(null);
    try {
      await action();
      refresh();
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      return false;
    } finally {
      setBusyId(null);
    }
  }

  const promote = (briefId: string) =>
    run(() => api("/api/projects", "POST", { briefId }), briefId);

  const setStage = (stageId: string, status: string) =>
    run(() => api(`/api/stages/${stageId}`, "PATCH", { status }), stageId);

  const setProject = (projectId: string, status: string) =>
    run(() => api(`/api/projects/${projectId}`, "PATCH", { status }), projectId);

  const setPhase = (projectId: string, phase: string) =>
    run(() => api(`/api/projects/${projectId}`, "PATCH", { phase }), projectId);

  const addStage = (projectId: string, title: string) =>
    run(
      () => api(`/api/projects/${projectId}/stages`, "POST", { title: title.trim() }),
      projectId
    );

  const deleteStage = (stageId: string) =>
    run(() => api(`/api/stages/${stageId}`, "DELETE"), stageId);

  return { isPending, error, busyId, refresh, promote, setStage, setProject, setPhase, addStage, deleteStage };
}
