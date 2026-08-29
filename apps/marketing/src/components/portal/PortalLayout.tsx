"use client";

import { SidebarInset, SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";
import { Separator } from "@/components/ui/separator";
import { PortalSidebar } from "@/components/portal/PortalSidebar";
import NotificationBell from "@/components/portal/NotificationBell";
import { Toaster } from "@/components/ui/sonner";

/**
 * Portal shell — the shadcn dashboard-01 layout for the app pages
 * (sidebar + inset header), standalone from the marketing chrome
 * (the AppShell skips /dashboard and /agency).
 */
export function PortalLayout({ children }: { children: React.ReactNode }) {
  return (
    <SidebarProvider>
      <PortalSidebar />
      <SidebarInset>
        <header className="flex h-14 shrink-0 items-center gap-2 border-b border-[var(--border)] bg-[var(--background)] px-4">
          <SidebarTrigger className="-ml-1 text-foreground" />
          <Separator orientation="vertical" className="mr-2 h-4 bg-[var(--border)]" />
          <div className="flex-1" />
          <NotificationBell />
        </header>
        <div className="flex flex-1 flex-col gap-4 p-4 md:p-6">{children}</div>
      </SidebarInset>
      <Toaster position="bottom-right" />
    </SidebarProvider>
  );
}
