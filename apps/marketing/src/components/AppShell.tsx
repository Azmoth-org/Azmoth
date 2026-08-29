"use client";

import { usePathname } from "@/i18n/navigation";
import Navigation from "@/components/Navigation";
import Footer from "@/components/Footer";
import CookieBanner from "@/components/CookieBanner";
import ChatFacade from "@/components/ChatFacade";
import LenisProvider from "@/components/LenisProvider";
import CustomCursor from "@/components/CustomCursor";
import CursorTrailAnimation from "@/components/CursorTrail";

/** Paths that render WITHOUT the site chrome (nav/footer/chat) — auth + app surfaces. */
const AUTH_PATHS = ["/login", "/forgot-password", "/reset-password", "/magic-link"];
const APP_PATHS = ["/dashboard", "/agency", "/admin", "/client"];

/**
 * App shell: the persistent chrome around page content. Skips the nav,
 * footer, cookie banner, and chat widget on auth routes (like LucaP's
 * separate auth layout) and on the app routes (which use the shadcn
 * dashboard-01 portal layout instead).
 */
export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isBare =
    AUTH_PATHS.some((p) => pathname === p || pathname.startsWith(`${p}/`)) ||
    APP_PATHS.some((p) => pathname === p || pathname.startsWith(`${p}/`));

  // Bare surfaces render without the custom cursor, so they must restore
  // the native one (globals.css hides it for the custom-cursor routes).
  // AUTH pages also stay dark in light mode (site-dark guard — glassmorph
  // design); the APP routes (/admin, /client) flip with the theme.
  if (isBare) {
    if (AUTH_PATHS.some((p) => pathname === p || pathname.startsWith(`${p}/`))) {
      return <div className="native-cursor site-dark">{children}</div>;
    }
    return <div className="native-cursor">{children}</div>;
  }

  return (
    <div className="site-dark">
      <CustomCursor />
      <CursorTrailAnimation />
      <Navigation />
      <main className="min-h-screen">
        <LenisProvider>{children}</LenisProvider>
      </main>
      <Footer />
      <CookieBanner />
      <ChatFacade />
    </div>
  );
}
