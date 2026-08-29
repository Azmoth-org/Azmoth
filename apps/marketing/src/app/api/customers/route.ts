import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/lib/auth";
import prisma from "@/lib/prisma";
import { isAdmin } from "@/lib/admin";

/** GET /api/customers — billable clients with their portal accounts + projects. Admin-only. */
export async function GET(request: NextRequest) {
  try {
    const session = await auth.api.getSession({ headers: request.headers });
    if (!session?.user) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    if (!isAdmin(session)) return NextResponse.json({ error: "Forbidden" }, { status: 403 });

    const customers = await prisma.customer.findMany({
      include: {
        user: {
          select: {
            id: true,
            name: true,
            email: true,
            slug: true,
            projects: {
              select: { id: true, name: true, status: true, phase: true, quote: true, updatedAt: true },
              orderBy: { updatedAt: "desc" },
            },
          },
        },
      },
      orderBy: { updatedAt: "desc" },
    });

    return NextResponse.json({ customers });
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ ok: false, error: message }, { status: 500 });
  }
}
