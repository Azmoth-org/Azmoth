import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/lib/auth";
import { initPayment, getPaymentDetails, parseWebhook } from "@/lib/konnect";

/**
 * Konnect payments (Tunisia) — CMI / e-Dinar / PayPal TN / Flous.
 *
 * POST /api/payments/konnect   — initiate a payment (signed-in user).
 *    body: { amount, currency?, note?, firstName?, lastName?, payerEmail? }
 *    → { payUrl } — redirect the client there.
 *
 * GET /api/payments/konnect    — Konnect's webhook (query: payment_ref).
 *    Verifies the real status via Get Payment Details, logs it, always 200.
 */
export async function POST(request: NextRequest) {
  try {
    const session = await auth.api.getSession({ headers: request.headers });
    if (!session?.user) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const body = await request.json();
    const amount = Number(body?.amount);
    if (!Number.isFinite(amount) || amount <= 0) {
      return NextResponse.json({ error: "amount is required (>0)" }, { status: 400 });
    }

    const result = await initPayment({
      amount,
      currency: (body?.currency as "TND" | "EUR" | "USD") ?? "TND",
      note: body?.note,
      firstName: session.user.name?.split(" ")[0],
      lastName: session.user.name?.split(" ").slice(1).join(" ") || undefined,
      payerEmail: session.user.email || undefined,
    });

    return NextResponse.json({ ok: true, payUrl: result.payUrl ?? null });
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    console.error("Konnect init error:", message);
    return NextResponse.json({ error: message }, { status: 500 });
  }
}

/** Konnect webhook receiver — GET with ?payment_ref=<id> (idempotent, always 200). */
export async function GET(request: NextRequest) {
  const { paymentRef, status } = parseWebhook(request.nextUrl.searchParams);
  console.log(`[Konnect webhook] payment_ref=${paymentRef ?? "?"} status=${status ?? "?"}`);

  if (paymentRef) {
    // Best-effort verification of the authoritative status
    try {
      const details = await getPaymentDetails(paymentRef);
      console.log(`[Konnect webhook] verified payment ${paymentRef}:`, JSON.stringify(details).slice(0, 400));
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      console.error(`[Konnect webhook] verification failed for ${paymentRef}: ${message}`);
    }
  }

  return NextResponse.json({ ok: true });
}
