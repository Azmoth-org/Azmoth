import { NextRequest, NextResponse } from "next/server";
import { getSession } from "@/lib/session";
import prisma from "@/lib/prisma";

/**
 * GET /api/notifications — list the current user's notifications + unread count.
 * POST /api/notifications — mark all as read.
 */
export async function GET(request: NextRequest) {
  const session = await getSession();
  if (!session) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const take = Math.min(Number(request.nextUrl.searchParams.get("take") ?? 30), 100);
  const [items, unread] = await Promise.all([
    prisma.notification.findMany({
      where: { userId: session.user.id },
      orderBy: { createdAt: "desc" },
      take,
    }),
    prisma.notification.count({ where: { userId: session.user.id, read: false } }),
  ]);

  return NextResponse.json({ items, unread });
}

export async function POST() {
  const session = await getSession();
  if (!session) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  await prisma.notification.updateMany({
    where: { userId: session.user.id, read: false },
    data: { read: true },
  });

  return NextResponse.json({ ok: true });
}
