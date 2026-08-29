import prisma from "@/lib/prisma";
import { notifyProjectStatus, notifyStageStatus } from "@/lib/notifications";
import { getPipelineTemplate } from "@/lib/pipelines";

export type ProjectStatus =
  | "proposed"
  | "approved"
  | "in_progress"
  | "launched"
  | "completed";

export type StageStatus = "pending" | "in_progress" | "review" | "done" | "blocked";

/**
 * Promote a brief to a Project, creating the pipeline stages from the
 * service template (or the custom "other" template).
 */
export async function promoteBriefToProject(
  briefId: string,
  opts?: { status?: ProjectStatus }
): Promise<{ id: string }> {
  const brief = await prisma.brief.findUnique({ where: { id: briefId } });
  if (!brief) throw new Error("Brief not found");

  const existing = await prisma.project.findUnique({ where: { briefId } });
  if (existing) return { id: existing.id };

  const template = getPipelineTemplate(brief.category);
  const project = await prisma.project.create({
    data: {
      briefId: brief.id,
      userId: brief.userId,
      name: brief.name || template.label || brief.category,
      category: brief.category || "other",
      status: opts?.status ?? "proposed",
      stages: {
        create: template.stages.map((s, i) => ({
          key: s.key,
          title: s.title,
          order: i,
          status: "pending",
        })),
      },
    },
  });

  // Mark the brief as promoted so the agency console doesn't re-offer it
  await prisma.brief.update({
    where: { id: brief.id },
    data: { status: "promoted" },
  });

  return { id: project.id };
}

/** Advance a stage to a new status, stamping started/completed timestamps. */
export async function setStageStatus(stageId: string, status: StageStatus) {
  const stage = await prisma.stage.findUnique({ where: { id: stageId } });
  if (!stage) throw new Error("Stage not found");
  const oldStatus = stage.status;

  const data: { status: StageStatus; startedAt?: Date | null; completedAt?: Date | null } = {
    status,
  };
  if (status === "in_progress" && !stage.startedAt) data.startedAt = new Date();
  if (status === "done") {
    if (!stage.startedAt) data.startedAt = stage.createdAt;
    data.completedAt = new Date();
  }
  if (status === "pending" || status === "blocked") {
    data.completedAt = null;
  }

  const updated = await prisma.stage.update({ where: { id: stageId }, data });

  // Re-evaluate project status whenever a stage changes
  await maybeRollProjectForward(stage.projectId);

  // Notify the client on an actual stage change
  if (status !== oldStatus) {
    void notifyStageStatus(updated);
  }
  return updated;
}

/** Set a project's status explicitly. */
export async function setProjectStatus(projectId: string, status: ProjectStatus) {
  const project = await prisma.project.findUnique({ where: { id: projectId } });
  if (!project) throw new Error("Project not found");
  if (project.status === status) return project;

  const updated = await prisma.project.update({ where: { id: projectId }, data: { status } });
  void notifyProjectStatus(updated, status);
  return updated;
}

/**
 * When every stage is done, mark the project completed.
 * When the first stage starts, mark the project in_progress (unless already launched/completed).
 */
async function maybeRollProjectForward(projectId: string) {
  const project = await prisma.project.findUnique({
    where: { id: projectId },
    include: { stages: true },
  });
  if (!project) return;

  const allDone = project.stages.length > 0 && project.stages.every((s) => s.status === "done");
  if (allDone && project.status !== "completed") {
    await prisma.project.update({
      where: { id: projectId },
      data: { status: "completed" },
    });
    return;
  }
  if (
    project.status === "proposed" ||
    project.status === "approved"
  ) {
    const anyStarted = project.stages.some((s) => s.status === "in_progress" || s.status === "review");
    if (anyStarted) {
      await prisma.project.update({
        where: { id: projectId },
        data: { status: "in_progress" },
      });
    }
  }
}
