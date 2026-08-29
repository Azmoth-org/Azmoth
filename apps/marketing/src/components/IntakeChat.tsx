"use client";

import { useRouter } from "next/navigation";
import { useLocale } from "next-intl";
import { useEffect, useRef, useState } from "react";
import { Turnstile } from "@marsidev/react-turnstile";
import {
  AssistantRuntimeProvider,
} from "@assistant-ui/react";
import { useChatRuntime } from "@assistant-ui/react-ai-sdk";
import { Thread } from "@/components/assistant-ui/thread";
import { TooltipProvider } from "@/components/ui/tooltip";

/* ─── Data extraction ─── */

interface IntakeData {
  name: string;
  company?: string;
  email: string;
  phone?: string;
  category?: string;
  description?: string;
  budget?: string;
  timeline?: string;
}

function getText(parts: Array<{ type: string; text?: string }>): string {
  return (parts ?? [])
    .filter((p) => p.type === "text")
    .map((p) => p.text ?? "")
    .join("\n");
}

function tryExtractData(text: string): IntakeData | null {
  const name = text.match(/name[:\s]*([^\n,]+)/i)?.[1]?.trim() || "";
  const email =
    text.match(/email[:\s]*([^\n,\s]+@[^\n,\s]+)/i)?.[1]?.trim() || "";
  if (!name || !email) return null;
  return {
    name,
    email,
    company:
      text.match(/company[:\s]*([^\n,]+)/i)?.[1]?.trim() ||
      (text.match(/organization[:\s]*([^\n,]+)/i)?.[1]?.trim() ?? undefined),
    phone: text.match(/phone[:\s]*([^\n,]+)/i)?.[1]?.trim() ?? undefined,
    category: text.match(/category[:\s]*([^\n,]+)/i)?.[1]?.trim() ?? undefined,
    description:
      text.match(/description[:\s]*([^\n,]+)/i)?.[1]?.trim() ?? undefined,
    budget: text.match(/budget[:\s]*([^\n,.]+)/i)?.[1]?.trim() ?? undefined,
    timeline: text.match(/timeline[:\s]*([^\n,]+)/i)?.[1]?.trim() ?? undefined,
  };
}

function generateRef(): string {
  const chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
  let s = "";
  for (let i = 0; i < 6; i++) s += chars[Math.floor(Math.random() * chars.length)];
  return `SD-${s}`;
}

/* ─── Summary card (existing app logic) ─── */

function SRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[10px] md:text-[11px] text-[var(--muted)] uppercase tracking-[0.05em] font-medium">{label}</span>
      <span className="text-[13px] md:text-[14px] text-white tracking-[-0.01em] truncate">{value}</span>
    </div>
  );
}

function SummaryCard({
  data,
  onEdit,
  onSubmit,
}: {
  data: IntakeData;
  onEdit: () => void;
  onSubmit: () => void;
}) {
  return (
    <div className="bg-[var(--surface)]/80 backdrop-blur-xl border border-[var(--border)] rounded-2xl p-4 md:p-6">
      <div className="max-w-3xl mx-auto">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-[15px] md:text-[17px] font-bold text-white tracking-[-0.02em] font-['Manrope',system-ui,sans-serif]">Project brief summary</h3>
          <span className="text-[11px] text-[var(--muted)] tracking-[0.05em] uppercase font-medium label-mono">Ready to submit</span>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 md:gap-3 mb-4">
          <SRow label="Name" value={data.name} />
          {data.company && <SRow label="Company" value={data.company} />}
          <SRow label="Email" value={data.email} />
          {data.phone && <SRow label="Phone" value={data.phone} />}
          {data.category && <SRow label="Category" value={data.category} />}
          {data.budget && <SRow label="Budget" value={data.budget} />}
          {data.timeline && <SRow label="Timeline" value={data.timeline} />}
        </div>
        {data.description && (
          <p className="text-[13px] text-[var(--muted)] mb-4 tracking-[-0.01em] leading-[1.5] line-clamp-2">{data.description}</p>
        )}
        <div className="flex gap-3">
          <button type="button" onClick={onEdit} className="flex-1 px-5 py-2.5 border border-[var(--border)] text-[var(--muted)] rounded-[10px] font-medium text-[14px] hover:text-white hover:border-white/20 transition-all duration-150 btn-press tracking-[-0.01em]">Continue chatting</button>
          <button type="button" onClick={onSubmit} className="flex-1 px-5 py-2.5 bg-[var(--accent)] text-white rounded-[10px] font-medium text-[14px] hover:opacity-90 transition-all duration-150 btn-press tracking-[-0.01em]">Submit brief ✓</button>
        </div>
      </div>
    </div>
  );
}

/* ─── Chat body — official assistant-ui Thread component ─── */

function IntakeChatBody({
  welcome,
  readyToSubmit,
  extractedData,
  onEdit,
  onSubmit,
}: {
  welcome: string;
  readyToSubmit: boolean;
  extractedData: IntakeData | null;
  onEdit: () => void;
  onSubmit: () => void;
}) {
  return (
    <div className="w-full flex flex-col">
      {!readyToSubmit && (
        <div className="flex justify-start mb-4 md:mb-5">
          <div className="max-w-[85%] md:max-w-[75%] rounded-2xl rounded-tl-[4px] px-4 md:px-5 py-2.5 md:py-3 bg-[var(--surface)] text-[var(--muted)] border border-[var(--border)] text-[14px] md:text-[15px] leading-[1.6] tracking-[-0.01em]">
            <span className="whitespace-pre-wrap">{welcome}</span>
          </div>
        </div>
      )}

      {readyToSubmit && extractedData && (
        <div className="w-full mt-6 mb-6">
          <SummaryCard data={extractedData} onEdit={onEdit} onSubmit={onSubmit} />
        </div>
      )}

      <div className="aui-thread-scope w-full min-h-0 flex-1">
        <Thread />
      </div>
    </div>
  );
}

/* ─── Chat session (runtime + provider) ─── */

function IntakeChatSession({
  welcome,
  readyToSubmit,
  extractedData,
  onDataExtracted,
  onConversation,
  onEdit,
  onSubmit,
}: {
  welcome: string;
  readyToSubmit: boolean;
  extractedData: IntakeData | null;
  onDataExtracted: (data: IntakeData) => void;
  onConversation: (messages: Array<{ role: string; text: string }>) => void;
  onEdit: () => void;
  onSubmit: () => void;
}) {
  const runtime = useChatRuntime({
    onFinish: (result) => {
      const text = getText(result.message.parts as Array<{ type: string; text?: string }>);
      if (text.includes("[READY_TO_SUBMIT]")) {
        const fullText = result.messages
          .map((m) => getText(m.parts as Array<{ type: string; text?: string }>))
          .join("\n");
        const data = tryExtractData(fullText);
        if (data) onDataExtracted(data);
      }
      onConversation(
        result.messages.map((m) => ({
          role: m.role,
          text: getText(m.parts as Array<{ type: string; text?: string }>),
        })),
      );
    },
  });

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <TooltipProvider>
        <IntakeChatBody
          welcome={welcome}
          readyToSubmit={readyToSubmit}
          extractedData={extractedData}
          onEdit={onEdit}
          onSubmit={onSubmit}
        />
      </TooltipProvider>
    </AssistantRuntimeProvider>
  );
}

/* ─── Main component ─── */

export default function IntakeChat() {
  const router = useRouter();
  const locale = useLocale();
  const [verified, setVerified] = useState(false);
  const [welcome, setWelcome] = useState<string | null>(null);
  const [readyToSubmit, setReadyToSubmit] = useState(false);
  const [extractedData, setExtractedData] = useState<IntakeData | null>(null);
  const [submitted, setSubmitted] = useState(false);
  const conversationRef = useRef<Array<{ role: string; text: string }>>([]);

  useEffect(() => {
    fetch("/api/chat")
      .then((r) => r.json())
      .then((data) => { if (data.welcome) setWelcome(data.welcome); })
      .catch(() => setWelcome("Hey! Welcome to Silkdev AI 🙌\n\nWhat's on your mind? 👇"));
  }, []);

  const handleDataExtracted = (data: IntakeData) => {
    setExtractedData(data);
    setReadyToSubmit(true);
  };

  const handleConversation = (messages: Array<{ role: string; text: string }>) => {
    conversationRef.current = messages;
  };

  const handleEdit = () => {
    setReadyToSubmit(false);
    setExtractedData(null);
  };

  const handleSubmitBrief = () => {
    if (!extractedData || submitted) return;
    setSubmitted(true);
    const ref = generateRef();
    const submission = {
      ...extractedData,
      ref,
      submittedAt: new Date().toISOString(),
      conversation: conversationRef.current,
    };
    const existing = JSON.parse(localStorage.getItem("silkdev_intakes") || "[]");
    existing.unshift(submission);
    localStorage.setItem("silkdev_intakes", JSON.stringify(existing));
    router.push(`/${locale}/intake/confirmation?ref=${ref}`);
  };

  return (
    <div className="pt-[120px] pb-[100px] bg-[var(--background)] min-h-screen">
      <div className="max-w-6xl mx-auto px-6 md:px-[40px]">
        {!verified ? (
          <div className="py-20 flex flex-col items-center justify-center">
            <div className="max-w-sm w-full text-center">
              <div className="w-14 h-14 rounded-2xl bg-[var(--accent)]/10 flex items-center justify-center mx-auto mb-6">
                <svg className="w-7 h-7 text-[var(--accent)]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                </svg>
              </div>
              <h2 className="text-[22px] font-bold text-white tracking-[-0.02em] mb-2 font-['Manrope',system-ui,sans-serif]">Verify you&apos;re human</h2>
              <p className="text-[14px] text-[var(--muted)] tracking-[-0.01em] mb-8 leading-[1.6]">
                Quick security check to keep our AI intake spam-free.
              </p>
              <div className="flex justify-center">
                <Turnstile
                  siteKey={process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY!}
                  onSuccess={() => setVerified(true)}
                  options={{ theme: "dark" }}
                />
              </div>
              <p className="mt-4 text-[11px] text-[var(--muted)]/50 tracking-[-0.01em]">
                Protected by Cloudflare Turnstile
              </p>
            </div>
          </div>
        ) : (
          <>
            <div className="mb-10">
              <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full border border-[var(--border)] bg-[var(--surface)]/50 mb-5">
                <div className="w-2 h-2 rounded-full bg-[var(--accent)] animate-pulse" />
                <span className="text-[13px] text-[var(--muted)] tracking-[0.05em] uppercase font-['Manrope',system-ui,sans-serif]">Silkdev AI Intake</span>
              </div>
              <div className="flex items-center justify-between">
                <div>
                  <h1 className="text-[36px] md:text-[42px] font-bold tracking-[-0.03em] leading-[1.15] text-white mb-3 font-['Manrope',system-ui,sans-serif]">
                    Start your project
                  </h1>
                  <p className="text-[17px] text-[var(--muted)] tracking-[-0.01em]">
                    Tell us about your idea — we&apos;ll help shape it.
                  </p>
                </div>
                <button type="button" onClick={() => window.location.reload()} className="px-4 py-2 border border-[var(--border)] text-[var(--muted)] rounded-[10px] text-[13px] hover:text-white hover:border-white/20 transition-all btn-press tracking-[-0.01em]">
                  Start over
                </button>
              </div>
            </div>

            {welcome ? (
              <IntakeChatSession
                welcome={welcome}
                readyToSubmit={readyToSubmit}
                extractedData={extractedData}
                onDataExtracted={handleDataExtracted}
                onConversation={handleConversation}
                onEdit={handleEdit}
                onSubmit={handleSubmitBrief}
              />
            ) : (
              <div className="max-w-3xl">
                <div className="flex justify-start mb-3 md:mb-4">
                  <div className="bg-[var(--surface)] border border-[var(--border)] rounded-2xl rounded-tl-[4px] px-5 py-3">
                    <div className="flex gap-1.5">
                      <span className="w-2 h-2 rounded-full bg-[var(--muted)]/40 typing-dot" style={{ animationDelay: "0ms" }} />
                      <span className="w-2 h-2 rounded-full bg-[var(--muted)]/40 typing-dot" style={{ animationDelay: "150ms" }} />
                      <span className="w-2 h-2 rounded-full bg-[var(--muted)]/40 typing-dot" style={{ animationDelay: "300ms" }} />
                    </div>
                  </div>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
