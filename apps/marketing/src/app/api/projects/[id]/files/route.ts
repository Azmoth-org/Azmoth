import { get, list } from "@vercel/blob";
import { type NextRequest, NextResponse } from "next/server";
import prisma from "@/lib/prisma";
import { getSession } from "@/lib/session";

/**
 * Project files.
 * GET ?pathname=... — serve a single private blob (owner/admin only).
 * GET (no pathname)  — list the project's files.
 * POST ?filename=... — upload (server upload, 4.5 MB cap).
 */
export async function GET(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
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

  const pathname = request.nextUrl.searchParams.get("pathname");

  // List mode
  if (!pathname) {
    const { blobs } = await list({ prefix: `projects/${id}/`, limit: 100 });
    return NextResponse.json({
      files: blobs.map((b) => ({
        pathname: b.pathname,
        url: b.url,
        size: b.size,
        uploadedAt: b.uploadedAt,
      })),
    });
  }

  // Single-file serve mode
  if (!pathname.startsWith(`projects/${id}/`)) {
    return NextResponse.json({ error: "Pathname does not belong to this project" }, { status: 403 });
  }

  const result = await get(pathname, { access: "private" });
  if (!result || result.statusCode !== 200) {
    return new NextResponse("Not found", { status: 404 });
  }

  return new NextResponse(result.stream, {
    headers: {
      "Content-Type": result.blob.contentType,
      "Content-Disposition": `inline; filename="${pathname.split("/").pop()}"`,
      "X-Content-Type-Options": "nosniff",
      "Cache-Control": "private, max-age=3600",
    },
  });
}
