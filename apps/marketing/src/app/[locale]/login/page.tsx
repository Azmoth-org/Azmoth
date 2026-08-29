"use client";

import { useRef, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { authClient } from "@/lib/auth-client";
import { Link } from "@/i18n/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { AuthProviders } from "@/components/AuthProviders";
import { AuthLayout } from "@/components/AuthLayout";

/**
 * Magic-link only auth: enter your email, we send a secure sign-in link.
 * First-time users get an account automatically when they click the link.
 * Google/LinkedIn OAuth remain as alternatives.
 */
export default function LoginPage() {
  const t = useTranslations("login");
  const locale = useLocale();
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const emailRef = useRef<HTMLInputElement>(null);

  const handleSend = async () => {
    if (!email) {
      setError(t("email"));
      return;
    }
    setError("");
    setLoading(true);
    try {
      const { error: err } = await authClient.signIn.magicLink({
        email,
        callbackURL: `/${locale}/dashboard`,
      });
      if (err) setError(t("errMagic"));
      else setSent(true);
    } catch {
      setError(t("errMagic"));
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthLayout>
      <div className="text-center">
        <h1 className="text-3xl font-medium tracking-tight text-foreground">{t("magicTitle")}</h1>
        <p className="text-muted-foreground mt-2 text-sm">{t("magicSub")}</p>
      </div>

      <div className="space-y-4">
        <AuthProviders />

        <div className="flex items-center gap-3 pt-2">
          <div className="h-px flex-1 bg-[var(--border)]" />
          <span className="text-xs text-muted-foreground">{t("or")}</span>
          <div className="h-px flex-1 bg-[var(--border)]" />
        </div>

        <div className="space-y-3">
          <Input
            ref={emailRef}
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSend()}
            placeholder="you@example.com"
            disabled={sent}
          />

          {sent ? (
            <p className="text-sm text-emerald-400">{t("magicSent")}</p>
          ) : error ? (
            <p className="text-sm text-red-400">{error}</p>
          ) : null}

          <Button className="w-full" onClick={handleSend} disabled={loading || sent}>
            {loading ? t("loading") : t("sendLink")}
          </Button>
        </div>
      </div>

      <p className="text-muted-foreground mt-6 text-center text-xs">
        {t("terms1")}{" "}
        <Link href="/terms" className="text-foreground duration-150 hover:text-[var(--accent)]">
          {t("terms")}
        </Link>{" "}
        {t("and")}{" "}
        <Link href="/privacy" className="text-foreground duration-150 hover:text-[var(--accent)]">
          {t("privacy")}
        </Link>
      </p>
    </AuthLayout>
  );
}
