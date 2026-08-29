import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/lib/auth";
import prisma from "@/lib/prisma";
import { isAdmin } from "@/lib/admin";

type Params = { params: Promise<{ id: string }> };

async function assertProjectAccess(request: NextRequest, id: string) {
  const session = await auth.api.getSession({ headers: request.headers });
  if (!session?.user) return { error: NextResponse.json({ error: "Unauthorized" }, { status: 401 }) };
  const project = await prisma.project.findUnique({ where: { id } });
  if (!project) return { error: NextResponse.json({ error: "Not found" }, { status: 404 }) };
  if (project.userId !== session.user.id && !isAdmin(session)) {
    return { error: NextResponse.json({ error: "Forbidden" }, { status: 403 }) };
  }
  return { project };
}

/** GET /api/projects/[id]/tasks — list planner tasks. POST — add one. */
export async function GET(request: NextRequest, { params }: Params) {
  const { id } = await params;
  const access = await assertProjectAccess(request, id);
  if ("error" in access) return access.error;

  const tasks = await prisma.task.findMany({
    where: { projectId: id },
    orderBy: [{ status: "asc" }, { order: "asc" }],
  });
  return NextResponse.json({ tasks });
}

export async function POST(request: NextRequest, { params }: Params) {
  const { id } = await params;
  const access = await assertProjectAccess(request, id);
  if ("error" in access) return access.error;

  const body = await request.json();
  const title = String(body?.title ?? "").trim();
  if (!title) return NextResponse.json({ error: "title is required" }, { status: 400 });
  const status = ["pending", "in_progress", "review", "done"].includes(body?.status)
    ? body.status
    : "pending";

  const count = await prisma.task.count({ where: { projectId: id } });
  const task = await prisma.task.create({
    data: { projectId: id, title, status, order: count },
  });
  return NextResponse.json({ ok: true, task }, { status: 201 });
}
