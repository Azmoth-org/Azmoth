"use client";

import { AssistantChatTransport, useChatRuntime } from "@assistant-ui/react-ai-sdk";
import { AssistantRuntimeProvider } from "@assistant-ui/react";
import { TooltipProvider } from "@/components/ui/tooltip";
import { GrokThread } from "@/components/assistant-ui/grok-thread";
import type { UIMessage } from "ai";

type HistoryMessage = {
  id: string;
  role: string;
  senderName?: string | null;
  content: string;
  createdAt: string;
};

/**
 * Project chat — the AI SILKDEV rep for a specific project.
 * Wired to /api/projects/[id]/chat (project + client + memory context,
 * planner + memory tools). Uses the official assistant-ui Thread.
 * The persisted conversation (AI/client/admin) is seeded into the thread.
 */
export default function ProjectChat({
  projectId,
  projectName,
  history = [],
}: {
  projectId: string;
  projectName: string;
  history?: HistoryMessage[];
}) {
  const welcome: UIMessage = {
    id: "welcome",
    role: "assistant",
    parts: [
      {
        type: "text",
        text: `Hey — I'm your SILKDEV rep for **${projectName}**. Ask me where things stand, or tell me what you'd like next. I can also add tasks to your planner and remember your preferences for future chats.`,
      },
    ],
  };

  const seed: UIMessage[] = [
    welcome,
    ...history.map((m): UIMessage => ({
      id: m.id,
      role: m.role === "assistant" ? "assistant" : "user",
      parts: [
        {
          type: "text",
          text:
            m.role === "admin"
              ? `[STUDIO — ${m.senderName ?? "admin"}]: ${m.content}`
              : m.content,
        },
      ],
    })),
  ];

  const runtime = useChatRuntime({
    messages: seed,
    transport: new AssistantChatTransport({
      api: `/api/projects/${projectId}/chat`,
    }),
  });

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <TooltipProvider>
        <div className="h-[640px] overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface)]">
          <GrokThread />
        </div>
      </TooltipProvider>
    </AssistantRuntimeProvider>
  );
}
