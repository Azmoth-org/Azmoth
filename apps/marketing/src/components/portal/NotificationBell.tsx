"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { Bell, CheckCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

type Notification = {
  id: string;
  type: string;
  title: string;
  body: string | null;
  href: string | null;
  read: boolean;
  createdAt: string;
};

function relativeTime(iso: string, locale: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const rtf = new Intl.RelativeTimeFormat(locale, {
    numeric: "auto",
  });
  const mins = Math.round(diffMs / 60000);
  if (Math.abs(mins) < 1) return rtf.format(0, "minute");
  if (Math.abs(mins) < 60) return rtf.format(-mins, "minute");
  const hours = Math.round(mins / 60);
  if (Math.abs(hours) < 24) return rtf.format(-hours, "hour");
  return rtf.format(-Math.round(hours / 24), "day");
}

/** Portal notification bell — shadcn ghost icon button + Radix dropdown, polled while open. */
export default function NotificationBell() {
  const t = useTranslations("notifications");
  const locale = useLocale();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<Notification[]>([]);
  const [unread, setUnread] = useState(0);

  const load = async () => {
    try {
      const res = await fetch("/api/notifications", { cache: "no-store" });
      if (!res.ok) return;
      const data = await res.json();
      setItems(data.items ?? []);
      setUnread(data.unread ?? 0);
    } catch {
      /* session expired or offline — ignore */
    }
  };

  useEffect(() => {
    load();
    const interval = setInterval(load, 60000);
    return () => clearInterval(interval);
  }, []);

  const markRead = async (n: Notification) => {
    if (!n.read) {
      await fetch(`/api/notifications/${n.id}`, { method: "POST" });
      setUnread((u) => Math.max(0, u - 1));
      setItems((list) => list.map((x) => (x.id === n.id ? { ...x, read: true } : x)));
    }
    if (n.href) router.push(n.href);
    setOpen(false);
  };

  const markAll = async () => {
    await fetch("/api/notifications", { method: "POST" });
    setUnread(0);
    setItems((list) => list.map((x) => ({ ...x, read: true })));
  };

  return (
    <DropdownMenu
      open={open}
      onOpenChange={(o) => {
        setOpen(o);
        if (o) load();
      }}
    >
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          aria-label={t("title")}
          className="relative text-muted-foreground hover:text-foreground"
        >
          <Bell className="size-4" />
          {unread > 0 && (
            <span className="absolute right-1 top-1 h-2 w-2 rounded-full bg-[var(--accent)] ring-2 ring-[var(--background)]" />
          )}
        </Button>
      </DropdownMenuTrigger>

      <DropdownMenuContent align="end" className="w-80 border-[var(--border)] p-0">
        <DropdownMenuLabel className="flex items-center justify-between px-4 py-3">
          <span>{t("title")}</span>
          {unread > 0 && (
            <button
              type="button"
              onClick={markAll}
              className="inline-flex cursor-pointer items-center gap-1 text-xs text-muted-foreground transition-colors hover:text-foreground"
            >
              <CheckCheck className="size-3.5" />
              {t("markAll")}
            </button>
          )}
        </DropdownMenuLabel>
        <DropdownMenuSeparator />

        {items.length === 0 ? (
          <p className="px-4 py-10 text-center text-sm text-muted-foreground">{t("empty")}</p>
        ) : (
          items.map((n) => (
            <DropdownMenuItem
              key={n.id}
              onClick={() => markRead(n)}
              className="flex cursor-pointer items-start gap-2.5 px-4 py-3 focus:bg-foreground/5"
            >
              <span
                className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${
                  n.read ? "bg-foreground/15" : "bg-[var(--accent)]"
                }`}
              />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-foreground">{n.title}</p>
                {n.body && (
                  <p className="mt-0.5 line-clamp-2 text-xs leading-relaxed text-muted-foreground">
                    {n.body}
                  </p>
                )}
                <p className="mt-1 text-[11px] text-muted-foreground/70">
                  {relativeTime(n.createdAt, locale)}
                </p>
              </div>
            </DropdownMenuItem>
          ))
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
