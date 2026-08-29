import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/lib/auth";
import prisma from "@/lib/prisma";
import { isAdmin } from "@/lib/admin";

type Params = { params: Promise<{ id: string }> };

async function assertTaskAccess(request: NextRequest, id: string) {
  const session = await auth.api.getSession({ headers: request.headers });
  if (!session?.user) return { error: NextResponse.json({ error: "Unauthorized" }, { status: 401 }) };
  const task = await prisma.task.findUnique({ where: { id }, include: { project: true } });
  if (!task) return { error: NextResponse.json({ error: "Not found" }, { status: 404 }) };
  if (task.project.userId !== session.user.id && !isAdmin(session)) {
    return { error: NextResponse.json({ error: "Forbidden" }, { status: 403 }) };
  }
  return { task };
}

/** PATCH /api/tasks/[id] — update status (kanban columns) or rename. DELETE — remove. */
export async function PATCH(request: NextRequest, { params }: Params) {
  const { id } = await params;
  const access = await assertTaskAccess(request, id);
  if ("error" in access) return access.error;

  const body = await request.json();
  const data: { status?: string; title?: string } = {};
  // Kanban statuses: pending (To do) | in_progress | review | done.
  if (typeof body?.status === "string" && ["pending", "in_progress", "review", "done"].includes(body.status)) {
    data.status = body.status;
  }
  if (typeof body?.title === "string" && body.title.trim()) {
    data.title = body.title.trim();
  }
  if (Object.keys(data).length === 0) {
    return NextResponse.json({ error: "Nothing to update" }, { status: 400 });
  }

  const task = await prisma.task.update({ where: { id }, data });
  return NextResponse.json({ ok: true, task });
}

export async function DELETE(request: NextRequest, { params }: Params) {
  const { id } = await params;
  const access = await assertTaskAccess(request, id);
  if ("error" in access) return access.error;

  await prisma.task.delete({ where: { id } });
  return NextResponse.json({ ok: true });
}
