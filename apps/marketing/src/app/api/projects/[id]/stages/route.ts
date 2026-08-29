import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/lib/auth";
import prisma from "@/lib/prisma";
import { isAdmin } from "@/lib/admin";

type Params = { params: Promise<{ id: string }> };

/**
 * POST /api/projects/[id]/stages
 * Agency console: add a custom stage to a project's pipeline.
 * Admin-only.
 */
export async function POST(request: NextRequest, { params }: Params) {
  try {
    const session = await auth.api.getSession({ headers: request.headers });
    if (!session?.user) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
    if (!isAdmin(session)) {
      return NextResponse.json({ error: "Forbidden" }, { status: 403 });
    }

    const { id } = await params;
    const project = await prisma.project.findUnique({
      where: { id },
      include: { stages: { orderBy: { order: "desc" }, take: 1 } },
    });
    if (!project) {
      return NextResponse.json({ error: "Not found" }, { status: 404 });
    }

    const body = await request.json();
    const { title, key } = body ?? {};
    if (!title) {
      return NextResponse.json({ error: "title is required" }, { status: 400 });
    }

    const nextOrder = (project.stages[0]?.order ?? -1) + 1;
    const stage = await prisma.stage.create({
      data: {
        projectId: id,
        key: key || "custom",
        title,
        order: nextOrder,
        status: "pending",
      },
    });
    return NextResponse.json({ ok: true, stage });
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ ok: false, error: message }, { status: 500 });
  }
}
