"use client";

import { track } from "@/lib/analytics";

/** Opens the floating AI intake chat modal (dispatches the event ChatWidget listens for). */
export function openChat() {
  if (typeof window !== "undefined") {
    track("open_chat");
    window.dispatchEvent(new CustomEvent("silkdev:open-chat"));
  }
}
