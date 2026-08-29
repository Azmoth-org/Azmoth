/**
 * SILKDEV transactional email templates.
 *
 * Email-safe HTML: table-based, inline styles, 600px max, light background
 * (dark emails break in many clients), violet brand accent. The SILKDEV
 * logo is inlined as a data-URI (no external images — most clients block
 * them). Custom fonts aren't reliable in email, so the wordmark is styled
 * text in a bold system stack.
 */

const LOGO_DATA_URI = "data:image/png;base64,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";

const BRAND = {
  navy: "#0a0a14",
  violet: "#5a52e0",
  violetDeep: "#4a44c9",
  ink: "#111827",
  muted: "#6b7280",
  line: "#e5e7eb",
  bg: "#f4f4f7",
  card: "#ffffff",
};

/**
 * Google review short link — SILKDEV Google Business profile.
 * Used for the soft review ask in the client confirmation.
 */
const REVIEW_URL = "https://g.page/r/Ce1k_dejlVQyEBM/review";

function esc(value: unknown): string {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

/** Branded base shell: logo header, body slot, CTA, footer. */
export function emailLayout(opts: {
  title: string;
  bodyHtml: string;
  cta?: { label: string; href: string };
  footerNote?: string;
}): string {
  const ctaHtml = opts.cta
    ? `<table role="presentation" cellpadding="0" cellspacing="0" style="margin:28px 0 8px;">
        <tr><td style="border-radius:10px;background:${BRAND.violet};">
          <a href="${esc(opts.cta.href)}" style="display:inline-block;padding:13px 30px;color:#ffffff;font-size:14px;font-weight:700;text-decoration:none;border-radius:10px;">${esc(opts.cta.label)}</a>
        </td></tr>
      </table>`
    : "";
  const note = opts.footerNote
    ? `<p style="margin:18px 0 0;color:${BRAND.muted};font-size:12px;line-height:1.6;">${esc(opts.footerNote)}</p>`
    : "";
  const year = new Date().getFullYear();

  return `<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:${BRAND.bg};font-family:system-ui,-apple-system,'Segoe UI',Roboto,Arial,sans-serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:32px 16px;">
  <table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:${BRAND.card};border-radius:16px;overflow:hidden;border:1px solid ${BRAND.line};">

    <!-- Header: logo + wordmark -->
    <tr><td style="background:${BRAND.navy};padding:24px 32px;">
      <table role="presentation" cellpadding="0" cellspacing="0"><tr>
        <td style="vertical-align:middle;padding-right:12px;">
          <img src="${LOGO_DATA_URI}" width="36" height="36" alt="" style="display:block;border-radius:8px;" />
        </td>
        <td style="vertical-align:middle;">
          <div style="font-size:20px;font-weight:800;color:#ffffff;letter-spacing:2px;">SILKDEV</div>
          <div style="color:#8888a0;font-size:10px;letter-spacing:2px;text-transform:uppercase;margin-top:2px;">AI Development Agency &middot; Bizerte, Tunisia</div>
        </td>
      </tr></table>
    </td></tr>

    <!-- Body -->
    <tr><td style="padding:32px;">
      <h1 style="margin:0 0 16px;font-size:20px;font-weight:700;color:${BRAND.ink};line-height:1.3;">${esc(opts.title)}</h1>
      ${opts.bodyHtml}
      ${ctaHtml}
      ${note}
    </td></tr>

    <!-- Footer -->
    <tr><td style="background:#f8f8fa;padding:22px 32px;color:${BRAND.muted};font-size:12px;line-height:1.8;border-top:1px solid ${BRAND.line};">
      Silkdev-SUARL &middot; Bureau 5, Centre Aziza, 1er &eacute;tage, Av. de l'Ind&eacute;pendance, Menzel Bourguiba 7050, Tunisia<br/>
      <a href="mailto:contact@silkdev.com.tn" style="color:${BRAND.violet};text-decoration:none;">contact@silkdev.com.tn</a> &middot; &copy; ${year} Silkdev-SUARL. All rights reserved.
    </td></tr>

  </table>
</td></tr></table>
</body>
</html>`;
}

/** Client confirmation — a brief was received. */
export function briefClientTemplate({ name, ref }: { name: string; ref: string }): string {
  return emailLayout({
    title: `Thanks, ${esc(name || "there")} — we got it.`,
    bodyHtml: `
      <p style="margin:0 0 12px;color:${BRAND.ink};font-size:14px;line-height:1.7;">Your project brief has been received. Keep your reference handy:</p>
      <table role="presentation" cellpadding="0" cellspacing="0" style="margin:8px 0 20px;"><tr><td style="background:#f3f1ff;border:1px solid #ddd9ff;border-radius:10px;padding:10px 18px;font-size:14px;font-weight:700;color:${BRAND.violet};letter-spacing:0.5px;">${esc(ref)}</td></tr></table>
      <p style="margin:0;color:${BRAND.muted};font-size:14px;line-height:1.7;">Our team will review it and get back to you with next steps and a scoped quote — every project is quoted individually, no public price list, no surprises.</p>
      <p style="margin:20px 0 0;color:${BRAND.muted};font-size:13px;line-height:1.7;">If you enjoy working with us once your project ships, a <a href="${esc(REVIEW_URL)}" style="color:${BRAND.violet};text-decoration:underline;">Google review</a> helps a small studio enormously — here's the link for when you're ready.</p>`,
    footerNote: "You can track your project anytime in the SILKDEV client portal.",
  });
}

/** Studio notification — a new brief landed. */
export function briefStudioTemplate(b: {
  ref: string;
  name?: string | null;
  company?: string | null;
  email?: string | null;
  phone?: string | null;
  category?: string | null;
  budget?: string | null;
  timeline?: string | null;
  description?: string | null;
}): string {
  const rows = [
    ["Reference", b.ref],
    ["Name", b.name],
    ["Company", b.company],
    ["Email", b.email],
    ["Phone", b.phone],
    ["Category", b.category],
    ["Budget", b.budget],
    ["Timeline", b.timeline],
  ].filter(([, v]) => v);

  const tableRows = rows
    .map(
      ([k, v]) =>
        `<tr><td style="padding:9px 12px;border-bottom:1px solid ${BRAND.line};color:${BRAND.muted};font-size:13px;width:120px;">${esc(k)}</td><td style="padding:9px 12px;border-bottom:1px solid ${BRAND.line};color:${BRAND.ink};font-size:13px;font-weight:600;">${esc(v)}</td></tr>`,
    )
    .join("");

  return emailLayout({
    title: `New project brief — ${esc(b.ref)}`,
    bodyHtml: `
      <p style="margin:0 0 16px;color:${BRAND.muted};font-size:13px;">Received via the AI intake assistant.</p>
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border:1px solid ${BRAND.line};border-radius:10px;border-collapse:collapse;">${tableRows}</table>
      <h2 style="margin:24px 0 8px;font-size:14px;font-weight:700;color:${BRAND.ink};">Description</h2>
      <p style="margin:0;color:${BRAND.ink};font-size:14px;line-height:1.7;white-space:pre-wrap;">${esc(b.description || "—")}</p>`,
    cta: { label: "Open client portal", href: "https://silkdev.com.tn/en/dashboard" },
  });
}

/** Password reset (better-auth). */
export function resetPasswordTemplate({ url }: { url: string }): string {
  return emailLayout({
    title: "Reset your SILKDEV password",
    bodyHtml: `<p style="margin:0 0 4px;color:${BRAND.ink};font-size:14px;line-height:1.7;">Click below to choose a new password. This link expires shortly.</p>`,
    cta: { label: "Reset password", href: url },
    footerNote: "If you didn't request this, you can safely ignore this email.",
  });
}

/** Email verification (better-auth). */
export function verifyEmailTemplate({ url }: { url: string }): string {
  return emailLayout({
    title: "Verify your SILKDEV email",
    bodyHtml: `<p style="margin:0 0 4px;color:${BRAND.ink};font-size:14px;line-height:1.7;">Confirm your email address to activate your SILKDEV account.</p>`,
    cta: { label: "Verify email", href: url },
    footerNote: "If you didn't create an account, you can safely ignore this email.",
  });
}

/** Magic link sign-in (better-auth magic link). */
export function magicLinkTemplate({ url }: { url: string }): string {
  return emailLayout({
    title: "Sign in to SILKDEV",
    bodyHtml: `<p style="margin:0 0 4px;color:${BRAND.ink};font-size:14px;line-height:1.7;">Click the button below to sign in to your SILKDEV account. This link is single-use and expires shortly.</p>`,
    cta: { label: "Sign in to SILKDEV", href: url },
    footerNote: "If you didn't request this sign-in, you can safely ignore this email.",
  });
}

/** Generic event notification (project/stage/brief updates). */
export function notificationTemplate({
  title,
  body,
  cta,
}: {
  title: string;
  body: string;
  cta?: { label: string; href: string };
}): string {
  return emailLayout({
    title,
    bodyHtml: `<p style="margin:0;color:${BRAND.ink};font-size:14px;line-height:1.7;">${esc(body)}</p>`,
    cta: cta ? { label: cta.label, href: cta.href } : undefined,
  });
}
