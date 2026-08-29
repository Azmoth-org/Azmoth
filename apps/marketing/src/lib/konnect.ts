/**
 * Konnect (Global Net International) payment gateway — Tunisia.
 *
 * Docs: https://docs.konnect.network
 * Live base:     https://api.konnect.network/api/v2
 * Sandbox base:  https://api.sandbox.konnect.network/api/v2
 *
 * Flow:
 *   1. initPayment()  → POST /payments/init-payment → { payUrl, paymentRef }
 *   2. Redirect the payer to payUrl (CMI, e-Dinar, PayPal TN, Flous, …).
 *   3. Konnect GETs your webhook URL with ?payment_ref=<id>.
 *   4. Verify the real status via getPaymentDetails(payment_ref).
 *
 * Auth & payload (verified against the Konnect sandbox):
 *   - x-api-key header = the merchant "Secret" (dashboard → API).
 *   - receiverWalletId = the merchant's wallet ID.
 *   - token field      = the CURRENCY code (TND | EUR | USD), not a payment token.
 *
 * Env:
 *   KONNECT_MODE                        — "live" (default) | "sandbox"
 *   KONNECT_API_URL                     — overrides the live base URL
 *   KONNECT_MERCHANT_TOKEN              — live x-api-key (Secret)
 *   KONNECT_RECEIVER_WALLET_ID          — live receiver wallet ID
 *   KONNECT_SANDBOX_MERCHANT_TOKEN      — sandbox x-api-key (Secret)
 *   KONNECT_SANDBOX_RECEIVER_WALLET_ID  — sandbox receiver wallet ID
 *   KONNECT_WEBHOOK_URL                 — public URL Konnect notifies (GET with payment_ref)
 */

import crypto from "node:crypto";

export type KonnectCurrency = "TND" | "EUR" | "USD";

export interface InitPaymentInput {
  amount: number; // major units, e.g. 150 = 150 TND / 150.50 EUR
  currency?: KonnectCurrency;
  webhookUrl?: string;
  note?: string;
  orderId?: string;
  firstName?: string;
  lastName?: string;
  payerEmail?: string;
}

export interface KonnectInitResponse {
  payUrl?: string;
  paymentRef?: string;
  [key: string]: unknown;
}

const LIVE_API = process.env.KONNECT_API_URL || "https://api.konnect.network/api/v2";
const SANDBOX_API = "https://api.sandbox.konnect.network/api/v2";

const MODE: "live" | "sandbox" =
  process.env.KONNECT_MODE === "sandbox" ? "sandbox" : "live";

/** True when the gateway is pointed at the Konnect sandbox (local dev / testing). */
export function isSandboxMode(): boolean {
  return MODE === "sandbox";
}

/** Resolve the active API base URL for the current mode. */
export function konnectApiUrl(): string {
  return MODE === "sandbox" ? SANDBOX_API : LIVE_API;
}

function requireEnv(key: string): string {
  const value = process.env[key];
  if (!value) throw new Error(`${key} is not configured (mode=${MODE}, base=${konnectApiUrl()})`);
  return value;
}

function merchantToken(): string {
  return requireEnv(MODE === "sandbox" ? "KONNECT_SANDBOX_MERCHANT_TOKEN" : "KONNECT_MERCHANT_TOKEN");
}

function receiverWalletId(): string {
  return requireEnv(MODE === "sandbox" ? "KONNECT_SANDBOX_RECEIVER_WALLET_ID" : "KONNECT_RECEIVER_WALLET_ID");
}

function authHeaders(): Record<string, string> {
  return {
    "Content-Type": "application/json",
    "x-api-key": merchantToken(),
  };
}

/** Convert a major-unit amount to the gateway's minor units (TND → millimes, EUR/USD → centimes). */
export function toMinorUnits(amount: number, currency: KonnectCurrency = "TND"): number {
  return Math.round(amount * (currency === "TND" ? 1000 : 100));
}

/** Step 1 — create a payment request; returns the checkout URL to redirect the payer to. */
export async function initPayment(input: InitPaymentInput): Promise<KonnectInitResponse> {
  const currency = input.currency ?? "TND";
  const webhook = input.webhookUrl || requireEnv("KONNECT_WEBHOOK_URL");

  const body: Record<string, unknown> = {
    receiverWalletId: receiverWalletId(),
    token: currency, // currency code, per Konnect spec
    amount: toMinorUnits(input.amount, currency),
    type: "immediate",
    description: input.note || "",
    acceptedPaymentMethods: ["bank_card", "wallet", "e-DINAR"],
    orderId:
      input.orderId ||
      `silkdev-${crypto.randomBytes(5).toString("hex")}`,
    webhook,
    ...(input.firstName ? { firstName: input.firstName } : {}),
    ...(input.lastName ? { lastName: input.lastName } : {}),
    ...(input.payerEmail ? { email: input.payerEmail } : {}),
  };

  const res = await fetch(`${konnectApiUrl()}/payments/init-payment`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify(body),
  });

  const data = (await res.json().catch(() => ({}))) as KonnectInitResponse;
  if (!res.ok) {
    throw new Error(`Konnect init failed (${res.status}) [${MODE}@${konnectApiUrl()}]: ${JSON.stringify(data)}`);
  }
  return data;
}

/** Step 3/4 — fetch the authoritative payment status after the webhook fires. */
export async function getPaymentDetails(paymentId: string): Promise<Record<string, unknown>> {
  const res = await fetch(`${konnectApiUrl()}/payments/${paymentId}`, {
    method: "GET",
    headers: authHeaders(),
  });
  const data = (await res.json().catch(() => ({}))) as Record<string, unknown>;
  if (!res.ok) {
    throw new Error(`Konnect detail failed (${res.status}) [${MODE}@${konnectApiUrl()}]: ${JSON.stringify(data)}`);
  }
  return data;
}

/** Extract the payment id + status from a Konnect webhook GET (query params). */
export function parseWebhook(query: URLSearchParams): { paymentRef?: string; status?: string } {
  return {
    paymentRef: query.get("payment_ref") ?? query.get("paymentId") ?? undefined,
    status: query.get("status") ?? undefined,
  };
}
