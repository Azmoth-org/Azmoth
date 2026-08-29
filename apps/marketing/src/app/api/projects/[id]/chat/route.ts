import type { ModelMessage } from "ai";
import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";
import { auth } from "@/lib/auth";
import prisma from "@/lib/prisma";
import { isAdmin } from "@/lib/admin";
import { NoGatewayKeyError, streamChatWithFallback } from "@/lib/ai-gateway";

export const maxDuration = 60;

const STAGE_LABELS: Record<string, string> = {
  pending: "pending",
  in_progress: "in progress",
  review: "in review",
  done: "done",
  blocked: "blocked",
};

export async function GET(_request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const session = await auth.api.getSession({ headers: _request.headers });
  if (!session?.user) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const project = await prisma.project.findUnique({ where: { id } });
  if (!project) return NextResponse.json({ error: "Not found" }, { status: 404 });

  return NextResponse.json({
    welcome: `Hey ${session.user.name?.split(" ")[0] || "there"} 👋 — I'm your SILKDEV rep for **${project.name ?? "this project"}**. Ask me anything about where things stand, or tell me what you'd like to see next.`,
  });
}

export async function POST(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  try {
    const session = await auth.api.getSession({ headers: request.headers });
    if (!session?.user) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const { id } = await params;
    const project = await prisma.project.findUnique({
      where: { id },
      include: {
        stages: { orderBy: { order: "asc" } },
        brief: true,
        tasks: { orderBy: { order: "asc" } },
      },
    });
    if (!project) return NextResponse.json({ error: "Not found" }, { status: 404 });
    if (project.userId !== session.user.id && !isAdmin(session)) {
      return NextResponse.json({ error: "Forbidden" }, { status: 403 });
    }

    // ── Lifecycle: while an admin is in the conversation, client chat is off ──
    if (project.phase === "admin_review") {
      return NextResponse.json(
        { error: "The studio is reviewing your project right now — chat will reopen shortly." },
        { status: 409 },
      );
    }

    // ── Persisted conversation (AI/client/admin history) ──────────────────
    const history = await prisma.message.findMany({
      where: { projectId: id },
      orderBy: { createdAt: "asc" },
    });
    const historyMessages: ModelMessage[] = history.map((m) =>
      m.role === "assistant"
        ? { role: "assistant", content: m.content }
        : m.role === "admin"
          ? { role: "user", content: `[STUDIO — ${m.senderName ?? "admin"}]: ${m.content}` }
          : { role: "user", content: m.content },
    );

    // ── Context assembly ──────────────────────────────────────────────
    const memories = await prisma.clientMemory.findMany({
      where: { userId: session.user.id },
      orderBy: { createdAt: "desc" },
      take: 20,
    });
    const otherProjects = await prisma.project.count({
      where: { userId: session.user.id, id: { not: id } },
    });

    const doneStages = project.stages.filter((s) => s.status === "done").length;
    const progress = project.stages.length
      ? Math.round((doneStages / project.stages.length) * 100)
      : 0;

    const stagesText =
      project.stages.length === 0
        ? "(none yet)"
        : project.stages
            .map((s) => `- ${s.title ?? s.key}: ${STAGE_LABELS[s.status] ?? s.status}`)
            .join("\n");

    const tasksText =
      project.tasks.length === 0
        ? "(empty planner)"
        : project.tasks
            .map((t) => `- [${t.status === "done" ? "x" : " "}] ${t.title}`)
            .join("\n");

    const memoriesText =
      memories.length === 0
        ? "(nothing stored yet)"
        : memories.map((m) => `- ${m.note}`).join("\n");

    const SYSTEM_PROMPT = [
      `You are the SILKDEV project representative for ${session.user.name || "this client"}'s project "${project.name ?? "Untitled"}" (${project.category ?? "n/a"}).`,
      "You are the client's single point of contact at SILKDEV — friendly, direct, and honest. You talk like a real agency account manager, not a chatbot.",
      "",
      "## About the client",
      `- Name: ${session.user.name || "Unknown"} · Email: ${session.user.email}`,
      `- Has ${otherProjects} other project(s) with SILKDEV`,
      "",
      "## The project",
      `- Status: ${project.status} · Progress: ${progress}%`,
      `- Brief: ${project.brief?.description || "(no brief description)"}`,
      `- Scope: ${project.brief?.scope || "not specified"} · Category: ${project.category || "n/a"}`,
      "",
      "## Pipeline (stages)",
      stagesText,
      "",
      "## Planner tasks",
      tasksText,
      "",
      "## What you remember about this client",
      memoriesText,
      "",
      "## Your tools",
      "- remember_preference: save a durable fact about the client (preferences, communication style, goals, decisions). Use it whenever they share something worth remembering — it will inform every future conversation.",
      "- add_task / complete_task: manage the project planner together with the client.",
      "",
      "## Project lifecycle",
      `- Current phase: ${project.phase} — this drives how you behave:`,
      "  - intake: YOUR JOB IS TO COLLECT THE FULL SPEC. Ask one focused question at a time (goals, audience, pages/features, content, design references, timeline, budget). Do not move on until the previous answer is clear. When you have a complete picture, summarize the spec back and ask the client to confirm it. Once confirmed, say the project is ready for the studio's review and stop asking questions — a human from SILKDEV will take over from here.",
      "  - quoting/payment: answer questions about the quote and payment, but do not negotiate or change the quote.",
      "  - in_progress/iteration/delivery_review: report status from the pipeline and tasks above, and explain the change/iteration loop. Encourage the client to request changes in the chat whenever they want.",
      "  - completed: congratulate and offer next steps.",
      "  - admin_review: (should not reach you — chat is disabled during studio review)",
      "- Studio messages appear to the client as '[STUDIO — <name>]: …' — acknowledge them naturally if the client asks about them.",
      "",
      "Answer questions about the project from the context above. If you genuinely don't know something (e.g. exact dates), say you'll check with the team — never invent facts. Keep replies concise and human. The client can see the same pipeline and planner you can.",
    ].join("\n");

    const body = await request.json();
    const rawMessages: Array<{ role: string; content?: string; parts?: Array<{ type: string; text?: string }> }> =
      body.messages ?? [];

    // Convert UIMessage format (parts) to model message format (content)
    // The model sees the persisted conversation first, then this request's messages.
    const incoming: ModelMessage[] = rawMessages.map((msg) => {
      if (msg.content) {
        return { role: msg.role as "user" | "assistant", content: msg.content };
      }
      const text = msg.parts
        ?.filter((p) => p.type === "text")
        .map((p) => p.text ?? "")
        .join("\n");
      return { role: msg.role as "user" | "assistant", content: text || "" };
    });
    const messages = [...historyMessages, ...incoming];

    // Persist the new client message (conversation is stored in the Message table).
    const lastUser = [...incoming].reverse().find((m) => m.role === "user");
    if (lastUser?.content) {
      await prisma.message.create({
        data: { projectId: id, role: "user", content: String(lastUser.content) },
      });
    }

    try {
      return await streamChatWithFallback({
        system: SYSTEM_PROMPT,
        messages,
        maxSteps: 10,
        onFinish: async ({ text }) => {
          if (text) {
            await prisma.message.create({
              data: { projectId: id, role: "assistant", content: text },
            });
          }
        },
        tools: {
          remember_preference: {
            description:
              "Save a durable fact about the client (preferences, communication style, goals, decisions). Confirmed with the client before saving.",
            inputSchema: z.object({
              note: z.string().describe("The fact to remember, e.g. 'Prefers async updates over calls'"),
            }),
            execute: async ({ note }) => {
              await prisma.clientMemory.create({
                data: { userId: session.user.id, note, source: "ai" },
              });
              return { success: true, message: "Saved. I'll keep that in mind for our future conversations." };
            },
          },
          add_task: {
            description: "Add a task to the project planner.",
            inputSchema: z.object({
              title: z.string().describe("The task title"),
            }),
            execute: async ({ title }) => {
              const count = await prisma.task.count({ where: { projectId: id } });
              const task = await prisma.task.create({
                data: { projectId: id, title, order: count },
              });
              return { success: true, task: { id: task.id, title: task.title } };
            },
          },
          complete_task: {
            description: "Mark a planner task as done.",
            inputSchema: z.object({
              taskId: z.string().describe("The task id"),
            }),
            execute: async ({ taskId }) => {
              const task = await prisma.task.findUnique({ where: { id: taskId } });
              if (!task || task.projectId !== id) {
                return { success: false, message: "That task doesn't exist in this project." };
              }
              const updated = await prisma.task.update({ where: { id: taskId }, data: { status: "done" } });
              return { success: true, task: { id: updated.id, title: updated.title, status: updated.status } };
            },
          },
        },
      });
    } catch (error) {
      if (error instanceof NoGatewayKeyError) {
        return NextResponse.json({ error: error.message }, { status: 500 });
      }
      throw error;
    }
  } catch (error) {
    console.error("Project chat error:", error);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}
