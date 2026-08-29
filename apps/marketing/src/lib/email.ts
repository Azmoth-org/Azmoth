/**
 * Transactional email via ZeptoMail HTTP API.
 *
 * Env:
 *   ZEPTOMAIL_TOKEN   — API token (ZeptoMail → Account → API token)
 *   ZEPTOMAIL_SENDER  — verified sender address, e.g. noreply-<hash>@<bounce-domain>
 *   EMAIL_FROM_NAME   — display name (default "SILKDEV")
 *   EMAIL_TEST_OVERRIDE — while set, every email is redirected here instead of
 *                         the real recipient (safe testing; unset to send live)
 */

import { briefClientTemplate, briefStudioTemplate } from "@/lib/emailTemplates";

const ZEPTOMAIL_API = "https://api.zeptomail.com/v1.1/email";

export async function sendEmail({
  to,
  subject,
  html,
  text,
}: {
  to: string;
  subject: string;
  html?: string;
  text?: string;
}): Promise<boolean> {
  const testOverride = process.env.EMAIL_TEST_OVERRIDE;
  const actualTo = testOverride || to;
  const actualSubject =
    testOverride && testOverride !== to ? `[test → ${to}] ${subject}` : subject;

  const token = process.env.ZEPTOMAIL_TOKEN;
  const sender = process.env.ZEPTOMAIL_SENDER;
  if (!token || !sender) {
    console.warn(
      "ZeptoMail not configured (ZEPTOMAIL_TOKEN / ZEPTOMAIL_SENDER missing) — email skipped",
    );
    return false;
  }

  try {
    const res = await fetch(ZEPTOMAIL_API, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Zoho-enczapikey ${token}`,
      },
      body: JSON.stringify({
        from: {
          address: sender,
          name: process.env.EMAIL_FROM_NAME || "SILKDEV",
        },
        to: [{ email_address: { address: actualTo } }],
        subject: actualSubject,
        ...(html ? { htmlbody: html } : {}),
        ...(text ? { textbody: text } : {}),
      }),
    });
    if (!res.ok) {
      const body = await res.text();
      console.error("ZeptoMail error:", res.status, body.slice(0, 500));
      return false;
    }
    return true;
  } catch (error) {
    console.error("ZeptoMail send failed:", error);
    return false;
  }
}

/** Studio notification + client confirmation for a submitted intake brief. */
export async function notifyBriefSubmitted({
  ref,
  name,
  company,
  email,
  phone,
  category,
  budget,
  timeline,
  description,
}: {
  ref: string;
  name?: string | null;
  company?: string | null;
  email?: string | null;
  phone?: string | null;
  category?: string | null;
  budget?: string | null;
  timeline?: string | null;
  description?: string | null;
}): Promise<void> {
  const studioTo = process.env.BRIEFS_NOTIFY_EMAIL || "contact@silkdev.com.tn";

  // 1. Notify the studio
  await sendEmail({
    to: studioTo,
    subject: `New project brief ${ref} — ${category || "Intake"}`,
    html: briefStudioTemplate({ ref, name, company, email, phone, category, budget, timeline, description }),
  });

  // 2. Confirm to the client (only if they gave an email)
  if (email) {
    await sendEmail({
      to: email,
      subject: `We received your brief ${ref} — SILKDEV`,
      html: briefClientTemplate({ name: name || "", ref }),
    });
  }
}
