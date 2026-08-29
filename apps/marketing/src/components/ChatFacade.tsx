"use client";

import { lazy, Suspense, useEffect, useState } from "react";
import { usePathname } from "next/navigation";

const ChatWidget = lazy(() => import("@/components/ChatWidget"));

const OPEN_EVENT = "silkdev:open-chat";

/**
 * Facade for the chat (mirrors silklearn's Intercom facade).
 * A cheap static launcher button is always present; the ~230KB
 * assistant-ui bundle loads ONLY when the chat is actually opened
 * (launcher click or silkdev:open-chat from a CTA) — it never blocks
 * the critical path, hydration, or the page transition.
 *
 * Hidden on the contact page, where the page itself IS a full chat form.
 */
export default function ChatFacade() {
  const [ready, setReady] = useState(false);
  const [initialOpen, setInitialOpen] = useState(false);
  const pathname = usePathname();

  // No floating chat on /contact — the page embeds a full chat already.
  const hidden = pathname.endsWith("/contact");

  // CTAs dispatch silkdev:open-chat — load the widget on demand. If the
  // event arrives before mount, initialOpen carries it in; if after, the
  // widget's own listener opens it.
  useEffect(() => {
    const onOpen = () => {
      setInitialOpen(true);
      setReady(true);
    };
    window.addEventListener(OPEN_EVENT, onOpen);
    return () => window.removeEventListener(OPEN_EVENT, onOpen);
  }, []);

  const open = () => {
    setInitialOpen(true);
    setReady(true);
  };

  if (hidden) return null;

  return (
    <>
      {!ready && (
        <button
          type="button"
          onClick={open}
          aria-label="Chat with us"
          className="fixed bottom-5 right-5 z-40 w-14 h-14 rounded-full bg-[var(--accent)] text-white flex items-center justify-center shadow-xl shadow-[var(--accent)]/25 hover:scale-105 active:scale-95 transition-all duration-200 btn-press cursor-pointer"
        >
          {/* SILKDEV "S" monogram as the launcher icon (solid white on the
              accent pill — brightness-0 → black, invert → white). */}
          <img
            src="/images/silkdev.avif"
            alt=""
            draggable={false}
            className="w-8 h-8 object-contain brightness-0 invert"
          />
        </button>
      )}
      {ready && (
        <Suspense fallback={null}>
          <ChatWidget initialOpen={initialOpen} />
        </Suspense>
      )}
    </>
  );
}
