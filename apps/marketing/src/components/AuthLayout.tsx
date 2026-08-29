"use client";

import Image from "next/image";
import { Link } from "@/i18n/navigation";
import { Card, CardContent } from "@/components/ui/card";
import AuthBackgroundShape from "@/components/AuthBackgroundShape";

/**
 * Split-screen auth layout (ported from LucaP's app/auth/layout.tsx):
 * left = brand row + dotted-shape backdrop behind the form card,
 * right = a dimmed, grayscale image panel (hidden on mobile).
 */
export function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="dusk grid min-h-svh w-full bg-background lg:grid-cols-2">
      <div className="flex flex-col gap-4 p-6 md:p-10">
        {/* Brand row */}
        <Link href="/" className="flex items-center gap-2 font-medium">
          <div className="flex size-8 items-center justify-center rounded-lg bg-foreground/10">
            <img src="/favicon.svg" alt="" className="size-5" />
          </div>
          <span className="text-lg font-semibold tracking-tight text-foreground font-['Drystick',system-ui,sans-serif]">
            SILKDEV
          </span>
        </Link>

        <div className="flex flex-1 items-center justify-center">
          <div className="w-full max-w-lg">
            <div className="relative flex items-center justify-center px-4 py-10 sm:px-6 lg:px-8">
              <div className="absolute">
                <AuthBackgroundShape />
              </div>
              <Card className="relative z-10 w-full gap-6 border border-white/10 bg-[rgba(15,15,26,0.55)] py-6 backdrop-blur-xl sm:max-w-lg shadow-2xl shadow-black/30">
                <CardContent className="px-6">{children}</CardContent>
              </Card>
            </div>
          </div>
        </div>
      </div>

      {/* Right image panel */}
      <div className="relative hidden bg-muted lg:block">
        <Image
          src="/images/auth-bg.jpg"
          alt=""
          className="absolute inset-0 h-full w-full object-cover brightness-[0.35] grayscale"
          width={1920}
          height={1080}
          priority
        />
      </div>
    </div>
  );
}
