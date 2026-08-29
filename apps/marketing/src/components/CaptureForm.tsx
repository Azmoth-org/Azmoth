"use client";

import { useState } from "react";
import type { FormEvent } from "react";
import { Check, Loader2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { authClient } from "@/lib/auth-client";

/* Unique short reference for this submission (same alphabet as the chat intake). */
function generateRef(): string {
  const chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
  let s = "";
  for (let i = 0; i < 6; i++) {
    s += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  return s;
}

/* The single field accepts an email OR a phone number — pick the API slot by shape. */
function looksLikePhone(value: string): boolean {
  return /^[+()\d\s.-]+$/.test(value) && /\d/.test(value);
}

type Status = "idle" | "submitting" | "success" | "error";

/**
 * One-field lead capture: leave an email or phone number and we get back to
 * you within 24 hours. Lightweight alternative to the AI intake chat — no
 * chat, no multi-step form. Same submission flow as ChatWidget's
 * handleSubmitBrief: anonymous session, then POST /api/briefs.
 */
export default function CaptureForm() {
  const t = useTranslations("capture");
  const [value, setValue] = useState("");
  const [status, setStatus] = useState<Status>("idle");
  const [touched, setTouched] = useState(false);

  const trimmed = value.trim();
  const isPhone = looksLikePhone(trimmed);
  const submitting = status === "submitting";

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const contact = trimmed;
    if (!contact || submitting) return;

    setStatus("submitting");
    try {
      // Ensure an anonymous session so POST /api/briefs accepts the request
      // (returns 401 otherwise).
      const { data: existing } = await authClient.getSession();
      if (!existing?.session) {
        const anon = await authClient.signIn.anonymous();
        if (anon.error) throw new Error(anon.error.message || "Failed to create session");
      }

      const ref = generateRef();
      const res = await fetch("/api/briefs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: "",
          email: isPhone ? "" : contact,
          phone: isPhone ? contact : "",
          category: "general",
          description: "One-field capture (no full brief)",
          ref,
          conversation: [],
        }),
      });
      const json = await res.json().catch(() => ({}));
      if (!res.ok || !json.ok) {
        throw new Error(json.error || "Failed to submit");
      }
      setStatus("success");
    } catch {
      setStatus("error");
    }
  }

  const showRequired = touched && trimmed.length === 0 && status !== "error";
  const placeholder = isPhone ? t("phonePlaceholder") : t("emailPlaceholder");

  return (
    <div className="dusk rounded-2xl bg-card p-6 ring-1 ring-ring/60 sm:p-8">
      {status === "success" ? (
        <div className="flex items-center gap-4" role="status">
          <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-[var(--accent)]/15 text-[var(--accent)]">
            <Check className="size-5" />
          </span>
          <p className="text-[15px] leading-relaxed text-foreground">{t("success")}</p>
        </div>
      ) : (
        <>
          <h2 className="text-lg font-semibold tracking-[-0.02em] text-foreground">
            {t("title")}
          </h2>
          <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">
            {t("subtitle")}
          </p>

          <form
            onSubmit={handleSubmit}
            noValidate
            className="mt-6 flex flex-col gap-3 sm:flex-row"
          >
            <label htmlFor="capture-contact" className="sr-only">
              {placeholder}
            </label>
            <input
              id="capture-contact"
              type="text"
              inputMode={isPhone ? "tel" : "email"}
              autoComplete={isPhone ? "tel" : "email"}
              value={value}
              placeholder={placeholder}
              onChange={(e) => {
                setValue(e.target.value);
                setTouched(false);
                if (status === "error") setStatus("idle");
              }}
              onBlur={() => setTouched(true)}
              className="h-12 w-full flex-1 rounded-full border border-[var(--border)] bg-input px-5 text-sm text-foreground placeholder:text-muted-foreground outline-none transition-colors focus:border-[var(--accent)]/70 focus:ring-2 focus:ring-[var(--accent)]/25"
            />
            <button
              type="submit"
              disabled={submitting || trimmed.length === 0}
              className="btn-press h-12 shrink-0 cursor-pointer rounded-full bg-[var(--accent)] px-7 text-sm font-medium text-white transition-all duration-150 hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {submitting ? (
                <Loader2 className="mx-auto size-4 animate-spin" />
              ) : (
                t("submit")
              )}
            </button>
          </form>

          <p aria-live="polite" className="mt-3 min-h-[18px] text-sm">
            {status === "error" && (
              <span className="text-[var(--destructive)]">{t("error")}</span>
            )}
            {showRequired && (
              <span className="text-muted-foreground">{t("required")}</span>
            )}
          </p>
        </>
      )}
    </div>
  );
}
