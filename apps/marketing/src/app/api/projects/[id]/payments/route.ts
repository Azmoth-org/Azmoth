import { NextResponse } from "next/server";
import prisma from "@/lib/prisma";
import { getSession } from "@/lib/session";
import { initPayment, type KonnectCurrency } from "@/lib/konnect";

/**
 * In-chat payment — client pays the quote deposit (or full amount) via Konnect.
 * POST {} → creates a Payment record + returns { payUrl } for the chat CTA.
 * Requires the project owner (or admin) and phase = payment.
 */
export async function POST(
  _req: Request,
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

  if (project.phase !== "payment") {
    return NextResponse.json({ error: `Payments open only during the payment phase (now: ${project.phase})` }, { status: 409 });
  }

  const quote = (project.quote ?? null) as { depositAmount?: number; total?: number; currency?: string } | null;
  const amount = quote?.depositAmount && quote.depositAmount > 0 ? quote.depositAmount : (quote?.total ?? 0);
  if (amount <= 0) {
    return NextResponse.json({ error: "No payable amount — the quote has no deposit or total" }, { status: 400 });
  }
  const currency = (quote?.currency ?? "TND") as KonnectCurrency;

  // Fire-and-forget verify loop is handled by the Konnect webhook; here we
  // just init the payment and return the redirect URL.
  const init = await initPayment({
    amount,
    currency,
    note: `SILKDEV project deposit — ${project.name ?? project.id}`,
    payerEmail: user.email ?? undefined,
  });

  await prisma.payment.create({
    data: {
      projectId: id,
      kind: "deposit",
      amount,
      currency,
      status: "pending",
      paymentRef: init.paymentRef ?? null,
    },
  });

  return NextResponse.json({ ok: true, payUrl: init.payUrl, amount, currency, paymentRef: init.paymentRef ?? null });
}
