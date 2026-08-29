import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/lib/auth";
import prisma from "@/lib/prisma";
import { setStageStatus, type StageStatus } from "@/lib/projects";
import { isAdmin } from "@/lib/admin";

type Params = { params: Promise<{ id: string }> };

function requireAdmin(session: { user?: { id?: string; email?: string | null; role?: string | null } | null } | null): string | null {
  if (!session?.user) return "Unauthorized";
  if (!isAdmin(session)) return "Forbidden";
  return null;
}

/**
 * PATCH /api/stages/[id]
 * Agency console: advance a stage (pending → in_progress → review → done / blocked).
 * Admin-only.
 */
export async function PATCH(request: NextRequest, { params }: Params) {
  try {
    const session = await auth.api.getSession({ headers: request.headers });
    const authError = requireAdmin(session);
    if (authError) {
      return NextResponse.json({ error: authError }, { status: authError === "Unauthorized" ? 401 : 403 });
    }

    const { id } = await params;
    const body = await request.json();
    const { status } = body ?? {};
    const allowed: StageStatus[] = ["pending", "in_progress", "review", "done", "blocked"];
    if (!allowed.includes(status)) {
      return NextResponse.json({ error: "Invalid status" }, { status: 400 });
    }

    const stage = await setStageStatus(id, status as StageStatus);
    return NextResponse.json({ ok: true, stage });
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ ok: false, error: message }, { status: 500 });
  }
}

/**
 * DELETE /api/stages/[id]
 * Agency console: remove a custom stage from a pipeline.
 * Admin-only.
 */
export async function DELETE(request: NextRequest, { params }: Params) {
  try {
    const session = await auth.api.getSession({ headers: request.headers });
    const authError = requireAdmin(session);
    if (authError) {
      return NextResponse.json({ error: authError }, { status: authError === "Unauthorized" ? 401 : 403 });
    }

    const { id } = await params;
    await prisma.stage.delete({ where: { id } });
    return NextResponse.json({ ok: true });
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ ok: false, error: message }, { status: 500 });
  }
}
