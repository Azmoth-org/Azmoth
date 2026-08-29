import { NextResponse } from "next/server";
import prisma from "@/lib/prisma";
import { getSession } from "@/lib/session";
import { sendEmail } from "@/lib/email";
import { notificationTemplate } from "@/lib/emailTemplates";

/**
 * Admin saves the final quote for a project → phase: quoting → payment.
 * body: { lineItems: [{label, amount, qty?}], currency, depositPercent }
 * The deposit amount is derived and returned (the client pays it in-chat).
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
  if (!isAdmin) return NextResponse.json({ error: "Forbidden" }, { status: 403 });

  const body = await req.json().catch(() => ({}));
  const lineItems = Array.isArray(body?.lineItems)
    ? body.lineItems.map((li: { label?: string; amount?: number; qty?: number }) => ({
        label: String(li?.label ?? "").trim(),
        amount: Number(li?.amount) || 0,
        qty: Number(li?.qty) || 1,
      })).filter((li: { label: string; amount: number }) => li.label && li.amount > 0)
    : [];

  if (lineItems.length === 0) {
    return NextResponse.json({ error: "lineItems are required" }, { status: 400 });
  }

  const currency = String(body?.currency ?? "TND").toUpperCase();
  const depositPercent = Math.min(100, Math.max(0, Number(body?.depositPercent) || 50));
  const total = lineItems.reduce((sum: number, li: { amount: number; qty: number }) => sum + li.amount * li.qty, 0);
  const depositAmount = Math.round(total * (depositPercent / 100) * 100) / 100;

  const quote = {
    lineItems,
    total: Math.round(total * 100) / 100,
    currency,
    depositPercent,
    depositAmount,
    createdAt: new Date().toISOString(),
  };

  const project = await prisma.project.update({
    where: { id },
    data: { quote: quote as unknown as object, phase: "payment" },
  });

  const owner = project.userId ? await prisma.user.findUnique({ where: { id: project.userId } }) : null;

  // Notify the client a quote is ready
  if (owner?.email) {
    void sendEmail({
      to: owner.email,
      subject: `Your quote is ready — ${project.name ?? "SILKDEV project"}`,
      html: notificationTemplate({
        title: "Your quote is ready",
        body: `A final quote (${quote.total.toFixed(2)} ${currency}) is waiting for you in your project. You can review it and pay the deposit right from the chat.`,
        cta: { label: "Open your project", href: "https://silkdev.com.tn/en/dashboard" },
      }),
    });
  }

  return NextResponse.json({ ok: true, phase: "payment", quote });
}
