import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/lib/auth";
import prisma from "@/lib/prisma";
import { promoteBriefToProject } from "@/lib/projects";
import { isAdmin } from "@/lib/admin";

/**
 * POST /api/projects
 * Agency console: promote a brief to a Project (creates pipeline stages
 * from the service template). Admin-only.
 */
export async function POST(request: NextRequest) {
  try {
    const session = await auth.api.getSession({ headers: request.headers });
    if (!session?.user) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
    if (!isAdmin(session)) {
      return NextResponse.json({ error: "Forbidden" }, { status: 403 });
    }

    const body = await request.json();
    const { briefId } = body ?? {};
    if (!briefId) {
      return NextResponse.json({ error: "briefId is required" }, { status: 400 });
    }

    const { id } = await promoteBriefToProject(briefId);
    return NextResponse.json({ ok: true, id });
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ ok: false, error: message }, { status: 500 });
  }
}

/**
 * GET /api/projects
 * Client portal: list the current user's projects with stages.
 */
export async function GET(request: NextRequest) {
  try {
    const session = await auth.api.getSession({ headers: request.headers });
    if (!session?.user) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const projects = await prisma.project.findMany({
      where: { userId: session.user.id },
      include: { stages: { orderBy: { order: "asc" } }, brief: true },
      orderBy: { createdAt: "desc" },
    });
    return NextResponse.json({ projects });
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ ok: false, error: message }, { status: 500 });
  }
}
