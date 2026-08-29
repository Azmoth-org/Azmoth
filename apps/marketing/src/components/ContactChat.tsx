"use client";

import { useEffect, useRef, useState } from "react";
import { DefaultChatTransport } from "ai";
import { Turnstile } from "@marsidev/react-turnstile";
import { AssistantRuntimeProvider } from "@assistant-ui/react";
import { useChatRuntime } from "@assistant-ui/react-ai-sdk";
import { Thread } from "@/components/assistant-ui/thread";
import { TooltipProvider } from "@/components/ui/tooltip";
import { authClient } from "@/lib/auth-client";
import { useTranslations } from "next-intl";

/* ─── Data extraction (contact summary format) ─── */

interface ContactData {
  name: string;
  email: string;
  phone?: string;
  message: string;
}

function getText(parts: Array<{ type: string; text?: string }>): string {
  return (parts ?? [])
    .filter((p) => p.type === "text")
    .map((p) => p.text ?? "")
    .join("\n");
}

function tryExtractContact(text: string): ContactData | null {
  const name = text.match(/name[:：\s]*([^\n,]+)/i)?.[1]?.trim() || "";
  const email = text.match(/email[:：\s]*([^\n,\s]+@[^\n,\s]+)/i)?.[1]?.trim() || "";
  const phone = text.match(/phone[:：\s]*([^\n,]+)/i)?.[1]?.trim() || "";
  const message = text.match(/message[:：\s]*([\s\S]+)/i)?.[1]?.trim() || "";
  if (!name || !message) return null;
  if (!email && !phone) return null;
  return { name, email, phone: phone || undefined, message };
}

function generateRef(): string {
  const chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
  let s = "";
  for (let i = 0; i < 6; i++) s += chars.charAt(Math.floor(Math.random() * chars.length));
  return `SD-${s}`;
}

/* ─── Summary card ─── */

function SRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[10px] md:text-[11px] text-[var(--muted)] uppercase tracking-[0.05em] font-medium">{label}</span>
      <span className="text-[13px] md:text-[14px] text-white tracking-[-0.01em] break-words">{value}</span>
    </div>
  );
}

function ContactSummaryCard({
  data,
  onEdit,
  onSubmit,
  submitting,
  labels,
}: {
  data: ContactData;
  onEdit: () => void;
  onSubmit: () => void;
  submitting: boolean;
  labels: { summaryTitle: string; readyLabel: string; submit: string; continueChatting: string };
}) {
  return (
    <div className="bg-[var(--surface)]/80 backdrop-blur-xl border border-[var(--border)] rounded-2xl p-4 md:p-6">
      <div className="max-w-3xl mx-auto">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-[15px] md:text-[17px] font-bold text-white tracking-[-0.02em] font-['Manrope',system-ui,sans-serif]">{labels.summaryTitle}</h3>
          <span className="text-[11px] text-[var(--muted)] tracking-[0.05em] uppercase font-medium label-mono">{labels.readyLabel}</span>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2 md:gap-3 mb-4">
          <SRow label="Name" value={data.name} />
          {data.email && <SRow label="Email" value={data.email} />}
          {data.phone && <SRow label="Phone" value={data.phone} />}
        </div>
        <p className="text-[13px] text-[var(--muted)] mb-4 tracking-[-0.01em] leading-[1.5]">{data.message}</p>
        <div className="flex gap-3">
          <button type="button" onClick={onEdit} disabled={submitting} className="flex-1 px-5 py-2.5 border border-[var(--border)] text-[var(--muted)] rounded-[10px] font-medium text-[14px] hover:text-white hover:border-white/20 transition-all duration-150 btn-press tracking-[-0.01em] disabled:opacity-40">
            {labels.continueChatting}
          </button>
          <button type="button" onClick={onSubmit} disabled={submitting} className="flex-1 px-5 py-2.5 bg-[var(--accent)] text-white rounded-[10px] font-medium text-[14px] hover:opacity-90 transition-all duration-150 btn-press tracking-[-0.01em] disabled:opacity-40">
            {submitting ? "..." : labels.submit}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ─── Chat body (welcome + summary + official Thread) ─── */

function ContactChatBody({
  welcome,
  readyToSubmit,
  extractedData,
  submitting,
  onEdit,
  onSubmit,
  labels,
}: {
  welcome: string;
  readyToSubmit: boolean;
  extractedData: ContactData | null;
  submitting: boolean;
  onEdit: () => void;
  onSubmit: () => void;
  labels: { summaryTitle: string; readyLabel: string; submit: string; continueChatting: string };
}) {
  return (
    <div className="w-full h-full min-h-0 flex flex-col">
      {!readyToSubmit && (
        <div className="flex justify-start mb-4 md:mb-5">
          <div className="max-w-[85%] md:max-w-[75%] rounded-2xl rounded-tl-[4px] px-4 md:px-5 py-2.5 md:py-3 bg-[var(--surface)] text-[var(--muted)] border border-[var(--border)] text-[14px] md:text-[15px] leading-[1.6] tracking-[-0.01em]">
            <span className="whitespace-pre-wrap">{welcome}</span>
          </div>
        </div>
      )}

      {readyToSubmit && extractedData && (
        <div className="w-full mt-6 mb-6">
          <ContactSummaryCard data={extractedData} onEdit={onEdit} onSubmit={onSubmit} submitting={submitting} labels={labels} />
        </div>
      )}

      <div className="aui-thread-scope w-full min-h-0 flex-1">
        <Thread />
      </div>
    </div>
  );
}

/* ─── Chat session (runtime + provider) ─── */

function ContactChatSession({
  welcome,
  readyToSubmit,
  extractedData,
  submitting,
  onDataExtracted,
  onConversation,
  onEdit,
  onSubmit,
  labels,
}: {
  welcome: string;
  readyToSubmit: boolean;
  extractedData: ContactData | null;
  submitting: boolean;
  onDataExtracted: (data: ContactData) => void;
  onConversation: (messages: Array<{ role: string; text: string }>) => void;
  onEdit: () => void;
  onSubmit: () => void;
  labels: { summaryTitle: string; readyLabel: string; submit: string; continueChatting: string };
}) {
  const runtime = useChatRuntime({
    // Default transport posts to /api/chat; the contact flow targets the
    // same route with ?mode=contact (contact welcome + contact prompt).
    transport: new DefaultChatTransport({ api: "/api/chat?mode=contact" }),
    onFinish: (result) => {
      const text = getText(result.message.parts as Array<{ type: string; text?: string }>);
      if (text.includes("[READY_TO_SUBMIT]")) {
        const fullText = result.messages
          .map((m) => getText(m.parts as Array<{ type: string; text?: string }>))
          .join("\n");
        const data = tryExtractContact(fullText);
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
        <ContactChatBody
          welcome={welcome}
          readyToSubmit={readyToSubmit}
          extractedData={extractedData}
          submitting={submitting}
          onEdit={onEdit}
          onSubmit={onSubmit}
          labels={labels}
        />
      </TooltipProvider>
    </AssistantRuntimeProvider>
  );
}

/* ─── Main component: gate → chat → submit → success ─── */

export default function ContactChat() {
  const t = useTranslations("contact");
  const [verified, setVerified] = useState(false);
  const [welcome, setWelcome] = useState<string | null>(null);
  const [readyToSubmit, setReadyToSubmit] = useState(false);
  const [extractedData, setExtractedData] = useState<ContactData | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState(false);
  const [sentRef, setSentRef] = useState<string | null>(null);
  const conversationRef = useRef<Array<{ role: string; text: string }>>([]);

  const fetchWelcome = () => {
    fetch("/api/chat?mode=contact")
      .then((r) => r.json())
      .then((data) => { if (data.welcome) setWelcome(data.welcome); })
      .catch(() => setWelcome(t("welcomeFallback")));
  };

  // Load the welcome message on mount — without this the chat card hangs
  // on the 3-dot loading state forever.
  useEffect(() => {
    fetchWelcome();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleDataExtracted = (data: ContactData) => {
    setExtractedData(data);
    setReadyToSubmit(true);
  };

  const handleConversation = (messages: Array<{ role: string; text: string }>) => {
    conversationRef.current = messages;
  };

  const handleEdit = () => {
    setReadyToSubmit(false);
    setExtractedData(null);
    setSubmitError(false);
  };

  const handleSubmit = async () => {
    if (!extractedData || submitting || sentRef) return;
    setSubmitting(true);
    setSubmitError(false);
    try {
      // Ensure an anonymous session so POST /api/briefs accepts the request.
      const { data: existing } = await authClient.getSession();
      if (!existing?.session) {
        const anon = await authClient.signIn.anonymous();
        if (anon.error) throw new Error(anon.error.message || "Failed to create session");
      }

      const ref = generateRef();
      const res = await fetch("/api/briefs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: extractedData.name,
          email: extractedData.email,
          phone: extractedData.phone,
          category: "contact",
          description: extractedData.message,
          ref,
          conversation: conversationRef.current,
        }),
      });
      const json = await res.json().catch(() => ({}));
      if (!res.ok || !json.ok) {
        throw new Error(json.error || "Failed to submit");
      }
      setSentRef(json.ref || ref);
    } catch {
      setSubmitError(true);
    } finally {
      setSubmitting(false);
    }
  };

  const handleReset = () => {
    setSentRef(null);
    setReadyToSubmit(false);
    setExtractedData(null);
    setSubmitError(false);
    setWelcome(null);
    conversationRef.current = [];
    fetchWelcome();
  };

  const labels = {
    summaryTitle: t("summaryTitle"),
    readyLabel: t("readyLabel"),
    submit: t("sendMessage"),
    continueChatting: t("continueChatting"),
  };

  return (
    <div className="glass rounded-2xl flex flex-col overflow-hidden h-[min(560px,calc(100dvh-210px))] md:h-[640px]">
      {/* Card header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--border)] bg-[var(--surface)]/50 backdrop-blur-sm flex-shrink-0">
        <div className="flex items-center gap-2.5">
          <div className="w-2 h-2 rounded-full bg-[var(--accent)] animate-pulse" />
          <span className="text-[13px] text-[var(--muted)] tracking-[0.05em] uppercase font-['Manrope',system-ui,sans-serif]">
            {t("chatBadge")}
          </span>
        </div>
        {!sentRef && welcome && (
          <button
            type="button"
            onClick={handleReset}
            className="px-3 py-1.5 border border-[var(--border)] text-[var(--muted)] rounded-[10px] text-[12px] hover:text-white hover:border-white/20 transition-all btn-press tracking-[-0.01em]"
          >
            {t("startOver")}
          </button>
        )}
      </div>

      {/* Body */}
      <div className="flex-1 min-h-0 flex flex-col">
        {!verified ? (
          <div className="flex-1 flex flex-col items-center justify-center px-6">
            <div className="max-w-sm w-full text-center">
              <div className="w-14 h-14 rounded-2xl bg-[var(--accent)]/10 flex items-center justify-center mx-auto mb-6">
                <svg className="w-7 h-7 text-[var(--accent)]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                </svg>
              </div>
              <h2 className="text-[22px] font-bold text-white tracking-[-0.02em] mb-2 font-['Manrope',system-ui,sans-serif]">{t("verifyTitle")}</h2>
              <p className="text-[14px] text-[var(--muted)] tracking-[-0.01em] mb-8 leading-[1.6]">{t("verifyBody")}</p>
              <div className="flex justify-center">
                <Turnstile
                  siteKey={process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY!}
                  onSuccess={() => setVerified(true)}
                  options={{ theme: "dark" }}
                />
              </div>
              <p className="mt-4 text-[11px] text-[var(--muted)]/50 tracking-[-0.01em]">{t("protectedBy")}</p>
            </div>
          </div>
        ) : sentRef ? (
          <div className="flex-1 flex flex-col items-center justify-center px-6">
            <div className="max-w-sm w-full text-center">
              <div
                className="w-16 h-16 rounded-full flex items-center justify-center mx-auto mb-6"
                style={{ background: "rgba(108,99,255,0.15)" }}
              >
                <svg className="w-8 h-8 text-[var(--accent)]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
              </div>
              <h2 className="text-[22px] font-bold text-white tracking-[-0.02em] mb-2 font-['Manrope',system-ui,sans-serif]">{t("successTitle")}</h2>
              <p className="text-[14px] text-[var(--muted)] tracking-[-0.01em] mb-6 leading-[1.6]">{t("successBody")}</p>
              <div className="glass rounded-2xl px-5 py-4 mb-8">
                <p className="text-[11px] text-[var(--muted)] uppercase tracking-[0.05em] mb-1 font-medium">{t("refLabel")}</p>
                <p className="text-[20px] font-bold text-white tracking-[-0.02em] font-['Manrope',system-ui,sans-serif]">{sentRef}</p>
              </div>
              <button
                type="button"
                onClick={handleReset}
                className="px-5 py-2.5 border border-[var(--border)] text-[var(--muted)] rounded-[10px] font-medium text-[13px] hover:text-white hover:border-white/20 transition-all duration-150 btn-press tracking-[-0.01em]"
              >
                {t("sendAnother")}
              </button>
            </div>
          </div>
        ) : welcome ? (
          <div className="flex-1 min-h-0 flex flex-col px-5 md:px-6 py-4">
            <ContactChatSession
              welcome={welcome}
              readyToSubmit={readyToSubmit}
              extractedData={extractedData}
              submitting={submitting}
              onDataExtracted={handleDataExtracted}
              onConversation={handleConversation}
              onEdit={handleEdit}
              onSubmit={handleSubmit}
              labels={labels}
            />
          </div>
        ) : (
          <div className="flex-1 flex items-start px-5 md:px-6 py-5">
            <div className="max-w-3xl w-full">
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
          </div>
        )}
      </div>

      {submitError && (
        <div className="flex-shrink-0 px-5 py-3 border-t border-[var(--destructive)]/30 bg-[var(--destructive)]/10">
          <p className="text-[13px] text-[var(--destructive)] tracking-[-0.01em]">{t("submitError")}</p>
        </div>
      )}
    </div>
  );
}
