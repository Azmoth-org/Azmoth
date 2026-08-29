import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/lib/auth";
import prisma from "@/lib/prisma";
import { setProjectStatus, type ProjectStatus } from "@/lib/projects";
import { isAdmin } from "@/lib/admin";
import { PROJECT_PHASES } from "@/lib/projectLifecycle";

type Params = { params: Promise<{ id: string }> };

/**
 * PATCH /api/projects/[id]
 * Agency console: set project status or move it to another lifecycle phase.
 * Admin-only.
 */
export async function PATCH(request: NextRequest, { params }: Params) {
  try {
    const session = await auth.api.getSession({ headers: request.headers });
    if (!session?.user) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
    if (!isAdmin(session)) {
      return NextResponse.json({ error: "Forbidden" }, { status: 403 });
    }

    const { id } = await params;
    const body = await request.json();
    const { status, phase } = body ?? {};

    if (phase !== undefined) {
      if (!PROJECT_PHASES.includes(phase)) {
        return NextResponse.json({ error: "Invalid phase" }, { status: 400 });
      }
      const project = await prisma.project.update({
        where: { id },
        data: { phase },
      });
      return NextResponse.json({ ok: true, project });
    }

    const allowed: ProjectStatus[] = ["proposed", "approved", "in_progress", "launched", "completed"];
    if (!allowed.includes(status)) {
      return NextResponse.json({ error: "Invalid status" }, { status: 400 });
    }

    const project = await setProjectStatus(id, status as ProjectStatus);
    return NextResponse.json({ ok: true, project });
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ ok: false, error: message }, { status: 500 });
  }
}

/**
 * GET /api/projects/[id]
 * Anyone with a session can fetch their own project (client portal detail view).
 */
export async function GET(request: NextRequest, { params }: Params) {
  try {
    const session = await auth.api.getSession({ headers: request.headers });
    if (!session?.user) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const { id } = await params;
    const project = await prisma.project.findUnique({
      where: { id },
      include: {
        stages: { orderBy: { order: "asc" } },
        brief: true,
        tasks: { orderBy: [{ status: "asc" }, { order: "asc" }] },
      },
    });
    if (!project) {
      return NextResponse.json({ error: "Not found" }, { status: 404 });
    }
    if (project.userId !== session.user.id && !isAdmin(session)) {
      return NextResponse.json({ error: "Forbidden" }, { status: 403 });
    }

    return NextResponse.json({ project });
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ ok: false, error: message }, { status: 500 });
  }
}
