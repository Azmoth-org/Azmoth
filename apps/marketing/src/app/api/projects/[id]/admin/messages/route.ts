import { NextResponse } from "next/server";
import prisma from "@/lib/prisma";
import { getSession } from "@/lib/session";
import { canUserChat } from "@/lib/projectLifecycle";

/**
 * Admin injection into a project conversation.
 * POST { content } — posts the admin message (name/avatar attached), sets the
 *                    project to admin_review (client chat off).
 * POST ?action=release — hands the conversation back to the client.
 * Requires an admin session.
 */
export async function POST(
  req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const session = await getSession();
  const user = session?.user;
  if (!user) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const isAdmin =
    user.role === "admin" ||
    (process.env.ADMIN_EMAILS || "").split(",").includes(user.email?.toLowerCase() ?? "");

  const project = await prisma.project.findUnique({ where: { id } });
  if (!project) return NextResponse.json({ error: "Not found" }, { status: 404 });
  if (!isAdmin) return NextResponse.json({ error: "Forbidden" }, { status: 403 });

  const url = new URL(req.url);
  const action = url.searchParams.get("action");
  const body = await req.json().catch(() => ({}));

  if (action === "release") {
    // Back to the client: resume the pre-injection phase (default intake).
    const resumed = project.phase === "admin_review" ? "intake" : project.phase;
    const updated = await prisma.project.update({
      where: { id },
      data: { phase: resumed },
    });
    return NextResponse.json({ ok: true, phase: updated.phase });
  }

  const content = String(body?.content ?? "").trim();
  if (!content) return NextResponse.json({ error: "content is required" }, { status: 400 });

  await prisma.$transaction([
    prisma.message.create({
      data: {
        projectId: id,
        role: "admin",
        senderName: user.name || user.email?.split("@")[0] || "Admin",
        content,
      },
    }),
    prisma.project.update({ where: { id }, data: { phase: "admin_review" } }),
  ]);

  return NextResponse.json({ ok: true, phase: "admin_review" });
}

/** GET the full persisted conversation (admin view). */
export async function GET(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const session = await getSession();
  const user = session?.user;
  if (!user) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const isAdmin =
    user.role === "admin" ||
    (process.env.ADMIN_EMAILS || "").split(",").includes(user.email?.toLowerCase() ?? "");

  const project = await prisma.project.findUnique({
    where: { id },
    include: { messages: { orderBy: { createdAt: "asc" } } },
  });
  if (!project) return NextResponse.json({ error: "Not found" }, { status: 404 });

  const isOwner = project.userId === user.id;
  if (!isAdmin && !isOwner) return NextResponse.json({ error: "Forbidden" }, { status: 403 });

  return NextResponse.json({
    phase: project.phase,
    quote: project.quote,
    paymentStatus: project.paymentStatus,
    chatDisabled: !canUserChat(project.phase),
    messages: project.messages.map((m) => ({
      id: m.id,
      role: m.role,
      senderName: m.senderName,
      senderAvatar: m.senderAvatar,
      content: m.content,
      createdAt: m.createdAt,
    })),
  });
}
