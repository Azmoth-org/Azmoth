import { NextResponse } from "next/server";
import prisma from "@/lib/prisma";
import { getSession } from "@/lib/session";

/**
 * Client lifecycle actions on a project.
 * POST { action: "modification" } — request changes → phase: iteration
 * POST { action: "delivery" }    — confirm final delivery → phase: completed
 * Requires the project owner (or admin).
 */
export async function POST(
  req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const session = await getSession();
  const user = session?.user;
  if (!user) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const project = await prisma.project.findUnique({ where: { id } });
  if (!project) return NextResponse.json({ error: "Not found" }, { status: 404 });

  const isOwner = project.userId === user.id;
  const isAdmin =
    user.role === "admin" ||
    (process.env.ADMIN_EMAILS || "").split(",").includes(user.email?.toLowerCase() ?? "");
  if (!isOwner && !isAdmin) return NextResponse.json({ error: "Forbidden" }, { status: 403 });

  const body = await req.json().catch(() => ({}));
  const action = String(body?.action ?? "");

  if (action === "modification") {
    if (project.phase === "completed") {
      // Reopen a delivered project for a new iteration round.
      const updated = await prisma.project.update({ where: { id }, data: { phase: "iteration" } });
      return NextResponse.json({ ok: true, phase: updated.phase });
    }
    if (project.phase !== "in_progress" && project.phase !== "iteration" && project.phase !== "delivery_review") {
      return NextResponse.json({ error: `Modifications only during delivery (now: ${project.phase})` }, { status: 409 });
    }
    const updated = await prisma.project.update({ where: { id }, data: { phase: "iteration" } });
    return NextResponse.json({ ok: true, phase: updated.phase });
  }

  if (action === "delivery") {
    if (project.phase === "completed") {
      return NextResponse.json({ ok: true, phase: "completed" });
    }
    if (project.phase !== "in_progress" && project.phase !== "iteration" && project.phase !== "delivery_review") {
      return NextResponse.json({ error: `Delivery confirmation only during delivery (now: ${project.phase})` }, { status: 409 });
    }
    const updated = await prisma.project.update({ where: { id }, data: { phase: "completed" } });
    return NextResponse.json({ ok: true, phase: updated.phase });
  }

  return NextResponse.json({ error: "action must be modification or delivery" }, { status: 400 });
}
