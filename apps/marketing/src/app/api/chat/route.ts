import type { ModelMessage } from "ai";
import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";
import { NoGatewayKeyError, streamChatWithFallback } from "@/lib/ai-gateway";

// Allow streaming responses up to 60 seconds
export const maxDuration = 60;

const WELCOME_MESSAGE =
  "Hey! Welcome to Silkdev AI 🙌\n\n" +
  "I'm here to help bring your project to life. Just tell me a bit about what you're looking for — " +
  "a web app, a mobile app, AI agent pipeline, or something else entirely — and I'll guide us through the rest.\n\n" +
  "What's on your mind? 👇";

const CONTACT_WELCOME_MESSAGE =
  "Hey! Welcome to Silkdev 👋\n\n" +
  "Ask me anything — a question about Silkdev, an idea you want to run by us, or just tell us what you need. " +
  "I'll make sure the right person gets back to you within 24 hours.\n\n" +
  "What's on your mind? 👇";

export async function GET(req: NextRequest) {
  const mode = req.nextUrl.searchParams.get("mode");
  return NextResponse.json({
    welcome: mode === "contact" ? CONTACT_WELCOME_MESSAGE : WELCOME_MESSAGE,
  });
}

const SYSTEM_PROMPT = [
  "You are Silkdev's AI intake assistant — a friendly, conversational project consultant.",
  "",
  "Your job is to have a natural conversation with potential clients to understand their project needs.",
  "Guide the conversation naturally, don't ask everything at once. Let it flow like a real conversation.",
  "",
  "## Information to collect (gather gradually):",
  "",
  "1. **Project category** — What do they need?",
  "   - Web Application (sites, dashboards, SaaS)",
  "   - Mobile App (iOS, Android, cross-platform)",
  "   - AI / Agent Pipeline (LLM integrations, agent workflows, automation)",
  "   - Fractional CTO (technical leadership, strategy)",
  "   - Design / UI-UX (brand identity, design systems)",
  "   - Something else",
  "",
  "2. **Project narrative** — What problem are they solving? What have they tried? Dream outcome? Target audience?",
  "",
  "3. **Scope** — Timeline, Team readiness, Technical spec level. Budget: ask if they have a range in mind, but tell them we don't publish prices — every project is scoped individually and quoted at fixed price after we understand the needs.",
  "",
  "4. **Contact info** — Name, company, **email or phone — AT LEAST ONE IS REQUIRED**. Gather contact early: the moment the project picture is clear, ask for the best way to reach them (email or phone). If they haven't shared at least one by summary time, ask again before summarizing. We follow up with every brief.",
  "",
  "5. **How they heard about us**",
  "",
  "6. **Discovery call preference** — If they want a call, ask for preferred dates. Use `check_availability` to find open slots and `book_calendar_meeting` to book it after they confirm.",
  "",
  "## Tools available to you:",
  "",
  "- **check_availability**: Check what time slots are open for a given date. Call this when someone wants to schedule a call.",
  "- **book_calendar_meeting**: Book a meeting slot after the user confirms the time. You need: their name, email, phone, date, time, and an optional note.",
  "",
  "## When you have the project details AND at least one contact method (email or phone):",
  "",
  "Say something like: \"Great, I have everything I need! Let me summarize your brief...\" then present a clean summary with each item on a new line using format:",
  "Category: ...",
  "Description: ...",
  "Budget: ... (write the range they shared, or \"To be quoted\" if they didn't)",
  "Timeline: ...",
  "Name: ...",
  "Company: ...",
  "Email: ...",
  "Phone: ...",
  "Discovery Call: ... (if booked, mention the date/time)",
  "",
  "Then ask: \"Does everything look right? Should I submit this brief?\"",
  "",
  "IMPORTANT: End your response with \"[READY_TO_SUBMIT]\" ONLY when the user confirms the summary is correct. Do NOT include this marker before the user confirms.",
  "",
  "## Style guidelines:",
  "- Be warm and enthusiastic but professional",
  "- Use emojis sparingly (one per message max)",
  "- Keep paragraphs short (2-3 sentences)",
  "- If they're vague, ask friendly clarifying questions",
  "- If someone asks about pricing, explain we don't publish prices: every project is scoped individually and quoted at fixed price after understanding their needs. Then steer back to understanding their needs first",
].join("\n");

const CONTACT_SYSTEM_PROMPT = [
  "You are Silkdev's AI contact assistant — a friendly, conversational point of contact for general inquiries.",
  "",
  "Your job is to have a natural conversation with visitors who want to get in touch. Keep it light and fast — this is NOT the full project intake; just find out what they need and collect the minimum to reply.",
  "",
  "## What to collect:",
  "1. **Their message** — what they're asking about: a question about Silkdev, working together, a project idea (a short description is enough), a partnership, anything.",
  "2. **Name**",
  "3. **Email or phone — AT LEAST ONE IS REQUIRED** so we can reply. If they only share one, that's fine.",
  "4. Optional: company, how they heard about us.",
  "",
  "If they clearly want to start a full project, you can mention that a detailed brief gets a proposal within 48 hours and offer to summarize what they shared so far — but don't force the full intake flow on a general question.",
  "",
  "## Tools available to you:",
  "- **check_availability**: Check what time slots are open for a given date. Call this when someone wants to schedule a call.",
  "- **book_calendar_meeting**: Book a meeting slot after the user confirms the time. You need: their name, email, phone, date, time, and an optional note.",
  "",
  "## When you have their message AND at least one contact method (email or phone):",
  "Say something like: \"Great, here's what I'll pass along:\" then present a clean summary with each item on a new line using format:",
  "Name: ...",
  "Email: ...",
  "Phone: ...",
  "Message: ...",
  "Discovery Call: ... (if booked, mention the date/time)",
  "",
  "Then ask: \"Does everything look right? Should I send this?\"",
  "",
  "IMPORTANT: End your response with \"[READY_TO_SUBMIT]\" ONLY when the user confirms the summary is correct. Do NOT include this marker before the user confirms.",
  "",
  "## Style guidelines:",
  "- Be warm and helpful but concise — this is a contact conversation, not a sales pitch",
  "- Use emojis sparingly (one per message max)",
  "- Keep paragraphs short (2-3 sentences)",
  "- If someone asks about pricing, explain we don't publish prices: every project is scoped individually and quoted at fixed price after understanding their needs",
  "- Tunisian context: we're based in Bizerte, Tunisia and work remote-first",
].join("\n");

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const mode: "contact" | "intake" = body.mode === "contact" ? "contact" : "intake";
    const rawMessages: Array<{ role: string; content?: string; parts?: Array<{ type: string; text?: string }> }> = body.messages;

    // Validate messages
    if (!rawMessages || !Array.isArray(rawMessages) || rawMessages.length === 0) {
      return new Response("Messages array is required", { status: 400 });
    }

    // Convert Vercel AI SDK UIMessage format (parts) to standard format (content)
    const messages = rawMessages.map((msg) => {
      if (msg.content) {
        return { role: msg.role as "user" | "assistant", content: msg.content };
      }
      const text = msg.parts
        ?.filter((p) => p.type === "text")
        .map((p) => p.text ?? "")
        .join("\n");
      return { role: msg.role as "user" | "assistant", content: text || "" };
    }) as Array<ModelMessage>;

    try {
      return await streamChatWithFallback({
        system: mode === "contact" ? CONTACT_SYSTEM_PROMPT : SYSTEM_PROMPT,
        messages,
        maxSteps: 10,
        tools: {
          check_availability: {
            description: "Check available meeting time slots for a given date. Returns array of open times.",
            inputSchema: z.object({
              date: z.string().describe("Date to check, format: YYYY-MM-DD"),
            }),
            execute: async ({ date }) => {
              // Mock availability — in production, query Google Calendar API
              const now = new Date();
              const requested = new Date(date);
              const dayDiff = Math.ceil((requested.getTime() - now.getTime()) / (1000 * 60 * 60 * 24));

              if (dayDiff < 0) {
                return { available: false, message: "That date is in the past. Please pick a future date." };
              }
              if (dayDiff > 30) {
                return { available: false, message: "We only book up to 30 days in advance. Pick a closer date." };
              }
              if (requested.getDay() === 0 || requested.getDay() === 6) {
                return { available: false, message: "Weekends are not available. Pick a weekday (Mon-Fri).", slots: [] };
              }

              // Business hours 09:00-17:00 CET
              const slots = ["09:00", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00"];
              return { available: true, date, slots, message: `Available slots for ${date}: ${slots.join(", ")} CET` };
            },
          },
          book_calendar_meeting: {
            description: "Book a Google Calendar meeting with the client. Requires name, email, date, and time.",
            inputSchema: z.object({
              name: z.string().describe("Client's full name"),
              email: z.string().email().describe("Client's email address"),
              phone: z.string().optional().describe("Client's phone number"),
              date: z.string().describe("Meeting date, format: YYYY-MM-DD"),
              time: z.string().describe("Meeting time, format: HH:MM"),
              note: z.string().optional().describe("Brief meeting agenda or notes"),
            }),
            execute: async ({ name, email, phone, date, time, note }) => {
              // In production: integrate with Google Calendar API
              // For now, log and return confirmation
              console.log(`[CALENDAR] Meeting booked: ${name} (${email}) on ${date} at ${time}${phone ? `, tel: ${phone}` : ""}${note ? `, note: ${note}` : ""}`);

              return {
                success: true,
                meeting: {
                  title: `Discovery Call — ${name}`,
                  date,
                  time,
                  duration: "30 min",
                  with: name,
                  email,
                },
                message: `Meeting confirmed for ${date} at ${time} CET with ${name}. A calendar invite will be sent to ${email}.`,
              };
            },
          },
        },
      });
    } catch (error) {
      if (error instanceof NoGatewayKeyError) {
        return new Response(
          JSON.stringify({ error: error.message }),
          { status: 500, headers: { "Content-Type": "application/json" } },
        );
      }
      throw error;
    }
  } catch (error) {
    console.error("Chat API error:", error);
    return new Response(
      JSON.stringify({ error: "Internal server error" }),
      { status: 500, headers: { "Content-Type": "application/json" } },
    );
  }
}
