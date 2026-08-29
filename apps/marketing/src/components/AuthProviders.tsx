"use client";

import { useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { authClient } from "@/lib/auth-client";
import { Button } from "@/components/ui/button";

const PROVIDERS = [
  {
    id: "google" as const,
    icon: (
      <svg className="size-4" viewBox="0 0 24 24">
        <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
        <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
        <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
        <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
      </svg>
    ),
  },
  {
    id: "linkedin" as const,
    icon: (
      <svg className="size-4" viewBox="0 0 24 24" fill="#0A66C2">
        <path d="M20.45 20.45h-3.55v-5.57c0-1.33-.03-3.04-1.85-3.04-1.85 0-2.14 1.45-2.14 2.94v5.67H9.35V9h3.41v1.56h.05c.48-.9 1.64-1.85 3.37-1.85 3.6 0 4.27 2.37 4.27 5.46v6.28zM5.34 7.43a2.06 2.06 0 1 1 0-4.12 2.06 2.06 0 0 1 0 4.12zM7.12 20.45H3.55V9h3.57v11.45zM22.22 0H1.77C.79 0 0 .77 0 1.72v20.56C0 23.23.79 24 1.77 24h20.45c.98 0 1.78-.77 1.78-1.72V1.72C24 .77 23.2 0 22.22 0z" />
      </svg>
    ),
  },
];

/** Google + LinkedIn OAuth buttons (LucaP pattern: authClient.signIn.social). */
export function AuthProviders({ signUp }: { signUp?: boolean }) {
  const locale = useLocale();
  const t = useTranslations("login");
  const [pending, setPending] = useState<string | null>(null);

  const handleClick = async (provider: "google" | "linkedin") => {
    setPending(provider);
    await authClient.signIn.social({
      provider,
      callbackURL: `/${locale}/dashboard`,
      errorCallbackURL: `/${locale}/login`,
    });
    setPending(null);
  };

  return (
    <div className="flex flex-col gap-3">
      {PROVIDERS.map(({ id, icon }) => (
        <Button
          key={id}
          type="button"
          variant="outline"
          onClick={() => handleClick(id)}
          disabled={pending !== null}
          className="w-full"
        >
          {icon}
          {pending === id
            ? "…"
            : t(signUp ? (id === "google" ? "signupGoogle" : "signupLinkedIn") : id === "google" ? "continueGoogle" : "continueLinkedIn")}
        </Button>
      ))}
    </div>
  );
}
