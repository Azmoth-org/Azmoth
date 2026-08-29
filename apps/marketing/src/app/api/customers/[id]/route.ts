import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/lib/auth";
import prisma from "@/lib/prisma";
import { isAdmin } from "@/lib/admin";

type Params = { params: Promise<{ id: string }> };

/** Billing-profile fields editable from the customers detail page. */
const EDITABLE = [
  "displayName",
  "title",
  "givenName",
  "familyName",
  "companyName",
  "primaryEmail",
  "alternateEmail",
  "primaryPhone",
  "mobile",
  "webAddress",
  "taxIdentifier",
  "notes",
] as const;

/** GET /api/customers/[id] — full billing profile + linked account + projects. Admin-only. */
export async function GET(request: NextRequest, { params }: Params) {
  try {
    const session = await auth.api.getSession({ headers: request.headers });
    if (!session?.user) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    if (!isAdmin(session)) return NextResponse.json({ error: "Forbidden" }, { status: 403 });

    const { id } = await params;
    const customer = await prisma.customer.findUnique({
      where: { id },
      include: {
        user: {
          select: {
            id: true,
            name: true,
            email: true,
            slug: true,
            projects: {
              include: { stages: { orderBy: { order: "asc" } } },
              orderBy: { updatedAt: "desc" },
            },
          },
        },
      },
    });
    if (!customer) return NextResponse.json({ error: "Not found" }, { status: 404 });

    return NextResponse.json({ customer });
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ ok: false, error: message }, { status: 500 });
  }
}

/** PATCH /api/customers/[id] — update the billing profile. Admin-only. */
export async function PATCH(request: NextRequest, { params }: Params) {
  try {
    const session = await auth.api.getSession({ headers: request.headers });
    if (!session?.user) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    if (!isAdmin(session)) return NextResponse.json({ error: "Forbidden" }, { status: 403 });

    const { id } = await params;
    const body = await request.json();
    const data: Record<string, unknown> = {};

    for (const field of EDITABLE) {
      if (typeof body?.[field] === "string") {
        data[field] = (body[field] as string).trim() || null;
      }
    }
    if (body?.billingAddress && typeof body.billingAddress === "object") {
      data.billingAddress = body.billingAddress;
    }
    if (body?.shippingAddress && typeof body.shippingAddress === "object") {
      data.shippingAddress = body.shippingAddress;
    }
    if (Object.keys(data).length === 0) {
      return NextResponse.json({ error: "Nothing to update" }, { status: 400 });
    }

    const customer = await prisma.customer.update({ where: { id }, data });
    return NextResponse.json({ ok: true, customer });
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ ok: false, error: message }, { status: 500 });
  }
}
