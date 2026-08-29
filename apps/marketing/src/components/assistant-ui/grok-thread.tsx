"use client";

import {
  AuiIf,
  MessagePrimitive,
  ThreadPrimitive,
  useAuiState,
} from "@assistant-ui/react";
import type { FC } from "react";
import {
  AssistantMessage,
  Composer,
  ThreadScrollToBottom,
  UserMessage,
} from "@/components/assistant-ui/thread";

/**
 * Grok-style thread (assistant-ui grok.tsx example, adapted to the SILKDEV
 * dark tokens): centered max-width viewport, logo empty state, message
 * header with timestamp + actions, and the pill composer pinned at the
 * bottom with the disclaimer line.
 */
export const GrokThread: FC = () => {
  const isEmpty = useAuiState((s) => s.thread.isEmpty);

  return (
    <ThreadPrimitive.Root className="flex h-full flex-col items-stretch bg-[var(--background)]">
      <ThreadPrimitive.Viewport
        turnAnchor="top"
        className="relative flex flex-1 flex-col overflow-x-auto overflow-y-scroll scroll-smooth"
      >
        <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col px-4 pt-8">
          <AuiIf condition={(s) => s.thread.isEmpty}>
            <div className="flex h-full flex-col items-center justify-center">
              <img src="/favicon.svg" alt="SILKDEV" className="mb-6 size-10" />
            </div>
          </AuiIf>

          <div className="mb-14 flex flex-col gap-y-6 empty:hidden">
            <ThreadPrimitive.Messages>{() => <ThreadMessage />}</ThreadPrimitive.Messages>
          </div>

          <ThreadPrimitive.ViewportFooter className="sticky bottom-0 mt-auto flex flex-col gap-2 pb-4">
            <ThreadScrollToBottom />
            <Composer />
            <p className="mx-auto w-full max-w-3xl pb-1 text-center text-xs text-muted-foreground">
              SILKDEV rep can make mistakes. Important details are confirmed with the studio.
            </p>
          </ThreadPrimitive.ViewportFooter>
        </div>
      </ThreadPrimitive.Viewport>
    </ThreadPrimitive.Root>
  );
};

const ThreadMessage: FC = () => {
  const role = useAuiState((s) => s.message.role);
  const isEditing = useAuiState((s) => s.message.composer.isEditing);

  if (isEditing) return <UserMessage />;
  if (role === "user") return <UserMessage />;
  return <AssistantMessage />;
};
