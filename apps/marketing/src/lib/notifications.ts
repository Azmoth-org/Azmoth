import prisma from "@/lib/prisma";
import { sendEmail } from "@/lib/email";
import { notificationTemplate } from "@/lib/emailTemplates";

export type NotificationType = "brief" | "project" | "stage" | "system";

/** Create an in-app notification row for a portal user. */
export async function createNotification({
  userId,
  type,
  title,
  body,
  href,
}: {
  userId: string | null | undefined;
  type: NotificationType;
  title: string;
  body?: string;
  href?: string;
}) {
  if (!userId) return null;
  return prisma.notification.create({ data: { userId, type, title, body, href } });
}

const PROJECT_LABELS: Record<string, string> = {
  proposed: "proposed",
  approved: "approved",
  in_progress: "in progress",
  launched: "launched",
  completed: "completed",
};

const STAGE_LABELS: Record<string, string> = {
  pending: "pending",
  in_progress: "in progress",
  review: "in review",
  done: "done",
  blocked: "blocked",
};

/**
 * Project status changed — notify the client (in-app + email).
 * Call AFTER the status was persisted, with the NEW status.
 */
export async function notifyProjectStatus(
  project: { id: string; name: string | null; userId: string | null },
  newStatus: string,
) {
  if (!project.userId) return;
  const label = PROJECT_LABELS[newStatus] ?? newStatus;
  const title = `Your project is now ${label}`;
  const body = `${project.name ?? "Your project"} moved to ${label}.`;
  const href = `/dashboard/${project.id}`;

  await createNotification({ userId: project.userId, type: "project", title, body, href });

  // Email the client (non-blocking, best-effort)
  const user = await prisma.user.findUnique({ where: { id: project.userId } });
  if (user?.email) {
    void sendEmail({
      to: user.email,
      subject: `Project update — ${label}`,
      html: notificationTemplate({
        title,
        body: body + " Track progress and next steps in your portal.",
        cta: { label: "Open project", href: `https://silkdev.vercel.app${href}` },
      }),
    });
  }
}

/**
 * Stage status changed — notify the client (in-app + email).
 */
export async function notifyStageStatus(
  stage: { id: string; projectId: string; title: string | null; status: string },
) {
  const project = await prisma.project.findUnique({
    where: { id: stage.projectId },
    include: { user: { select: { email: true } } },
  });
  if (!project?.userId) return;

  const label = STAGE_LABELS[stage.status] ?? stage.status;
  const title = `Stage ${label}: ${stage.title ?? "Stage"}`;
  const body = `"${stage.title ?? "Stage"}" is now ${label} on ${project.name ?? "your project"}.`;
  const href = `/dashboard/${project.id}`;

  await createNotification({ userId: project.userId, type: "stage", title, body, href });

  if (project.user?.email) {
    void sendEmail({
      to: project.user.email,
      subject: `Stage update — ${label}`,
      html: notificationTemplate({
        title,
        body: body + " See the full pipeline in your portal.",
        cta: { label: "Open project", href: `https://silkdev.vercel.app${href}` },
      }),
    });
  }
}
