"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import type { UIMessage } from "ai";
import { AssistantRuntimeProvider } from "@assistant-ui/react";
import { useChatRuntime } from "@assistant-ui/react-ai-sdk";
import { Thread } from "@/components/assistant-ui/thread";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Turnstile } from "@marsidev/react-turnstile";
import {
  Bot,
  BrainCircuit,
  Globe,
  Lightbulb,
  Palette,
  Smartphone,
} from "lucide-react";
import { authClient } from "@/lib/auth-client";
import { track } from "@/lib/analytics";
import { useTranslations } from "next-intl";
import { useLocale } from "next-intl";

/* ─── Types ─── */
type PrefilterSelection =
  | "web-app"
  | "mobile-app"
  | "ai-agent"
  | "fractional-cto"
  | "design"
  | "other"
  | null;

type Stage = "closed" | "prefilter" | "chat" | "submitting" | "done";

interface ChatWidgetProps {
  /** Mount straight into the prefilter screen (used by ChatFacade). */
  initialOpen?: boolean;
}

interface IntakeData {
  name: string;
  company: string;
  email: string;
  phone: string;
  category: string;
  description: string;
  budget: string;
  timeline: string;
}

interface SavedSession {
  stage: Stage;
  prefilter: PrefilterSelection;
  verified: boolean;
  readyToSubmit: boolean;
  extractedData: IntakeData | null;
  welcome: string | null;
  messages: UIMessage[];
}

const STORAGE_KEY = "silkdev_chat_session_v1";
const OPEN_EVENT = "silkdev:open-chat";

/* ─── Prefilter options ─── */
const PREFILTER_OPTIONS: Array<{ value: PrefilterSelection; labelKey: string; icon: React.ReactNode }> = [
  { value: "web-app", labelKey: "optWeb", icon: <Globe className="w-5 h-5" /> },
  { value: "mobile-app", labelKey: "optMobile", icon: <Smartphone className="w-5 h-5" /> },
  { value: "ai-agent", labelKey: "optAgent", icon: <Bot className="w-5 h-5" /> },
  { value: "fractional-cto", labelKey: "optCto", icon: <BrainCircuit className="w-5 h-5" /> },
  { value: "design", labelKey: "optDesign", icon: <Palette className="w-5 h-5" /> },
  { value: "other", labelKey: "optOther", icon: <Lightbulb className="w-5 h-5" /> },
];

/* ─── Helpers ─── */
function getText(parts: Array<{ type: string; text?: string }>): string {
  if (!parts) return "";
  return parts.filter((p) => p.type === "text").map((p) => p.text ?? "").join("\n");
}

function loadSession(): SavedSession | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return null;
    return parsed as SavedSession;
  } catch {
    return null;
  }
}

function saveSession(session: SavedSession) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
  } catch {
    /* storage full or unavailable — non-fatal */
  }
}

function clearSession() {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* ignore */
  }
}

function generateRef(): string {
  const chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
  let s = "";
  for (let i = 0; i < 6; i++) s += chars[Math.floor(Math.random() * chars.length)];
  return `SD-${s}`;
}

/* ─── Chat session — official assistant-ui Thread component ─── */

function ChatSession({
  initialMessages,
  welcome,
  readyToSubmit,
  extractedData,
  prefilterLabel,
  submitError,
  onDataExtracted,
  onMessagesChange,
  onEdit,
  onSubmit,
}: {
  initialMessages: UIMessage[];
  welcome: string | null;
  readyToSubmit: boolean;
  extractedData: IntakeData | null;
  prefilterLabel: string | null;
  submitError: string | null;
  onDataExtracted: (data: IntakeData) => void;
  onMessagesChange: (messages: UIMessage[]) => void;
  onEdit: () => void;
  onSubmit: () => void;
}) {
  const chat = useTranslations("chat");
  const runtime = useChatRuntime({
    messages: initialMessages,
    onFinish: (result) => {
      onMessagesChange(result.messages as UIMessage[]);
      const text = getText(result.message.parts as Array<{ type: string; text?: string }>);
      if (text.includes("[READY_TO_SUBMIT]")) {
        const fullText = result.messages
          .map((m) => getText(m.parts as Array<{ type: string; text?: string }>))
          .join("\n");
        const data = tryExtractData(fullText);
        if (data) onDataExtracted(data);
      }
    },
  });

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <TooltipProvider>
        <div className="w-full flex flex-col">
          {/* Prefilter chip */}
          {prefilterLabel && (
            <div className="pb-3">
              <span className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full border border-[var(--border)] bg-[var(--surface)]/50">
                <span className="text-[11px] text-[var(--muted)] tracking-[0.08em] uppercase">{prefilterLabel}</span>
              </span>
            </div>
          )}

          {submitError && (
            <div className="w-full mb-3 px-4 py-3 rounded-[12px] bg-red-500/10 border border-red-500/30 text-[13px] text-red-300 tracking-[-0.01em]">
              {submitError}
            </div>
          )}

          {/* Summary card — app-level UI above the Thread */}
          {readyToSubmit && extractedData && (
            <div className="w-full mb-6 rounded-xl border border-[var(--border)] overflow-hidden">
              <div className="px-5 py-4 border-b border-[var(--border)] bg-[var(--surface)]/50">
                <p className="text-[13px] font-semibold text-white tracking-[-0.01em]">{chat("briefTitle")}</p>
              </div>
              <div className="p-5 space-y-3 bg-[var(--surface)]/20">
                {[
                  ["fieldName", extractedData.name],
                  ["fieldCompany", extractedData.company],
                  ["fieldEmail", extractedData.email],
                  ["fieldPhone", extractedData.phone],
                  ["fieldCategory", extractedData.category],
                  ["fieldBudget", extractedData.budget],
                  ["fieldTimeline", extractedData.timeline],
                ].filter(([, v]) => v).map(([k, v]) => (
                  <div key={k as string} className="flex justify-between gap-4">
                    <span className="text-[13px] text-[var(--muted)] tracking-[-0.01em] flex-shrink-0">{k}</span>
                    <span className="text-[13px] text-white tracking-[-0.01em] text-right">{v as string}</span>
                  </div>
                ))}
                {extractedData.description && (
                  <p className="text-[13px] text-[var(--muted)] tracking-[-0.01em] pt-1">{extractedData.description}</p>
                )}
              </div>
              <div className="p-5 border-t border-[var(--border)] flex items-center justify-between gap-3">
                <button
                  type="button"
                  onClick={onEdit}
                  className="px-4 py-2.5 text-[13px] text-[var(--muted)] hover:text-white transition-colors btn-press tracking-[-0.01em]"
                >
                  {chat("edit")}
                </button>
                <button
                  type="button"
                  onClick={onSubmit}
                  className="px-5 py-2.5 bg-[var(--accent)] text-white rounded-[10px] text-[13px] font-medium hover:opacity-90 transition-all duration-150 btn-press tracking-[-0.01em]"
                >
                  {chat("submit")}
                </button>
              </div>
            </div>
          )}

          {/* Welcome bubble — shown until the first message arrives */}
          {welcome && !readyToSubmit && (
            <div className="w-full mb-4 flex justify-start">
              <div className="max-w-[85%] rounded-2xl rounded-tl-[4px] px-4 py-2.5 bg-[var(--surface)] text-[var(--muted)] border border-[var(--border)] text-[14px] leading-[1.55] tracking-[-0.01em]">
                <span className="whitespace-pre-wrap">{welcome}</span>
              </div>
            </div>
          )}

          {/* The official assistant-ui Thread */}
          <div className="aui-thread-scope w-full min-h-0 flex-1">
            <Thread />
          </div>
        </div>
      </TooltipProvider>
    </AssistantRuntimeProvider>
  );
}

/* ─── Main Widget ─── */
export default function ChatWidget({ initialOpen = false }: ChatWidgetProps) {
  const locale = useLocale();
  const chat = useTranslations("chat");
  const [stage, setStage] = useState<Stage>(initialOpen ? "prefilter" : "closed");
  const [prefilter, setPrefilter] = useState<PrefilterSelection>(null);
  const [verified, setVerified] = useState(false);
  const [readyToSubmit, setReadyToSubmit] = useState(false);
  const [extractedData, setExtractedData] = useState<IntakeData | null>(null);
  const [welcome, setWelcome] = useState<string | null>(null);
  const [briefRef, setBriefRef] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [chatMessages, setChatMessages] = useState<UIMessage[]>([]);
  const [sessionId, setSessionId] = useState(0);
  const restoredRef = useRef<SavedSession | null>(null);
  if (restoredRef.current === null && typeof window !== "undefined") {
    restoredRef.current = loadSession();
  }

  const restored = restoredRef.current;

  /* ── Restore session data on mount — but never auto-open the modal ── */
  useEffect(() => {
    const saved = restoredRef.current;
    if (!saved || saved.stage === "closed") return;
    setPrefilter(saved.prefilter);
    setVerified(saved.verified);
    setReadyToSubmit(saved.readyToSubmit);
    setExtractedData(saved.extractedData);
    setWelcome(saved.welcome);
    // stage intentionally NOT restored: the chat only opens on user click
  }, []);

  /* ── Fetch welcome (no AI tokens) when entering chat with no messages ── */
  useEffect(() => {
    if (stage !== "chat" || chatMessages.length > 0 || welcome) return;
    fetch("/api/chat")
      .then((r) => r.json())
      .then((data) => { if (data.welcome) setWelcome(data.welcome); })
      .catch(() => setWelcome(chat("welcomeFallback")));
  }, [stage, chatMessages.length, welcome]);

  /* ── Listen for "Start a project" trigger ── */
  useEffect(() => {
    const handler = () => openChat();
    window.addEventListener(OPEN_EVENT, handler);
    return () => window.removeEventListener(OPEN_EVENT, handler);
  }, []);

  /* ── Persist session on every state change ── */
  useEffect(() => {
    if (stage === "closed") return;
    saveSession({
      stage,
      prefilter,
      verified,
      readyToSubmit,
      extractedData,
      welcome,
      messages: chatMessages,
    });
  }, [stage, prefilter, verified, readyToSubmit, extractedData, welcome, chatMessages]);

  /* ── Body scroll lock when open ── */
  useEffect(() => {
    if (stage !== "closed") {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => { document.body.style.overflow = ""; };
  }, [stage]);

  const openChat = useCallback(() => {
    const saved = restoredRef.current;
    if (saved && saved.stage !== "closed") {
      setStage(saved.stage); // resume where the user left off — on click only
    } else {
      setStage("prefilter");
    }
  }, []);

  const closeChat = useCallback(() => {
    setStage("closed");
  }, []);

  const restart = useCallback(() => {
    clearSession();
    restoredRef.current = null;
    setSessionId((s) => s + 1);
    setChatMessages([]);
    setPrefilter(null);
    setVerified(false);
    setReadyToSubmit(false);
    setExtractedData(null);
    setWelcome(null);
    setBriefRef(null);
    setSubmitError(null);
    setStage("prefilter");
  }, []);

  const handleDataExtracted = useCallback((data: IntakeData) => {
    setExtractedData(data);
    // Hard gate: we follow up on every brief, so at least an email or a
    // phone number is required before anything can be submitted.
    setReadyToSubmit(Boolean(data.email?.trim() || data.phone?.trim()));
  }, []);

  const handleMessagesChange = useCallback((messages: UIMessage[]) => {
    setChatMessages(messages);
  }, []);

  const handleEdit = useCallback(() => {
    setReadyToSubmit(false);
    setExtractedData(null);
  }, []);

  /* ── Final submit: ensure anonymous session, then POST to /api/briefs ── */
  const handleSubmitBrief = useCallback(async () => {
    if (!extractedData) return;
    setStage("submitting");
    setSubmitError(null);
    try {
      const { data: existing } = await authClient.getSession();
      if (!existing?.session) {
        const anon = await authClient.signIn.anonymous();
        if (anon.error) throw new Error(anon.error.message || "Failed to create session");
      }

      const ref = generateRef();
      const conversation = chatMessages.map((m) => ({
        role: m.role,
        text: getText(m.parts as Array<{ type: string; text?: string }>),
      }));
      const res = await fetch("/api/briefs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...extractedData, ref, conversation }),
      });
      const json = await res.json().catch(() => ({}));
      if (!res.ok || !json.ok) {
        throw new Error(json.error || "Failed to submit");
      }
      setBriefRef(ref);
      track("brief_submitted", { category: extractedData?.category ?? "unknown", ref });
      setStage("done");
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setSubmitError(message);
      setStage("chat");
      setReadyToSubmit(true);
    }
  }, [extractedData, chatMessages]);

  if (stage === "closed") {
    return (
      <button
        type="button"
        onClick={openChat}
        aria-label="Chat with us"
        className="fixed bottom-5 right-5 z-40 w-14 h-14 rounded-full bg-[var(--accent)] text-white flex items-center justify-center shadow-xl shadow-[var(--accent)]/25 hover:scale-105 active:scale-95 transition-all duration-200 btn-press"
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
    );
  }

  const prefilterLabel = prefilter
    ? chat(PREFILTER_OPTIONS.find((o) => o.value === prefilter)?.labelKey ?? "")
    : null;

  return (
    <div className="fixed inset-0 z-[60] flex items-end sm:items-end sm:justify-end sm:p-6">
      {/* Backdrop — click to close */}
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={closeChat} aria-hidden="true" />

      {/* Modal panel — floating above the launcher on desktop, bottom sheet on mobile */}
      <div className="relative w-full sm:w-[430px] h-[92dvh] sm:h-[min(75vh,700px)] bg-[var(--background)] border border-[var(--border)] sm:rounded-2xl rounded-t-2xl flex flex-col overflow-hidden">
        {/* ── Top bar ── */}
        <header className="flex items-center justify-between px-5 md:px-6 h-14 border-b border-[var(--border)] bg-[var(--surface)]/50 backdrop-blur-sm flex-shrink-0">
          <div className="flex items-center gap-3">
            <span className="text-[16px] font-semibold tracking-tight text-white font-['Drystick',system-ui,sans-serif]">
              SILKDEV
            </span>
          </div>
          <div className="flex items-center gap-2">
            {stage === "chat" && (
              <button
                type="button"
                onClick={restart}
                className="px-3.5 py-2 text-[13px] text-[var(--muted)] hover:text-white border border-[var(--border)] hover:border-white/25 rounded-[10px] transition-all duration-150 btn-press tracking-[-0.01em]"
              >
                {chat("startOver")}
              </button>
            )}
            <button
              type="button"
              onClick={closeChat}
              aria-label="Close chat"
              className="w-10 h-10 flex items-center justify-center text-[var(--muted)] hover:text-white hover:bg-white/5 rounded-[10px] transition-colors duration-150 btn-press"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </header>

        {/* ── Body ── */}
        <div className="flex-1 overflow-y-auto">
          <div className="px-5 md:px-6 py-6 md:py-8 w-full flex flex-col">

            {/* PREFILTER */}
            {stage === "prefilter" && (
              <div className="flex flex-col items-center justify-center min-h-[45vh] text-center">
                <div className="w-14 h-14 rounded-2xl bg-[var(--accent)]/10 flex items-center justify-center mb-6">
                  <svg className="w-7 h-7 text-[var(--accent)]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                  </svg>
                </div>
                <h2 className="text-[24px] md:text-[26px] font-bold text-white tracking-[-0.03em] mb-3 font-['Manrope',system-ui,sans-serif]">
                  {chat("prefilterTitle")}
                </h2>
                <p className="text-[14px] text-[var(--muted)] tracking-[-0.01em] mb-7 max-w-md leading-[1.6]">
                  {chat("prefilterSub")}
                </p>
                <div className="grid grid-cols-1 gap-2.5 w-full max-w-sm">
                  {PREFILTER_OPTIONS.map((opt) => (
                    <button
                      key={opt.value}
                      type="button"
                      onClick={() => { setPrefilter(opt.value); setStage("chat"); }}
                      className="flex items-center gap-3 px-4 py-3 bg-[var(--surface)] border border-[var(--border)] rounded-[12px] text-left hover:border-[var(--accent)]/40 hover:bg-[var(--accent)]/5 transition-all duration-150 btn-press"
                    >
                      <span className="text-[var(--accent)] flex items-center">{opt.icon}</span>
                      <span className="text-[14px] font-medium text-white tracking-[-0.01em]">{chat(opt.labelKey)}</span>
                    </button>
                  ))}
                </div>
                <p className="mt-6 text-[11px] text-[var(--muted)]/50 tracking-[-0.01em]">
                  {chat("turnstileNote")}
                </p>
              </div>
            )}

            {/* CHAT */}
            {stage === "chat" && (
              <>
                {!verified ? (
                  <div className="py-14 flex flex-col items-center justify-center text-center">
                    <div className="max-w-sm w-full">
                      <div className="w-12 h-12 rounded-2xl bg-[var(--accent)]/10 flex items-center justify-center mx-auto mb-5">
                        <svg className="w-6 h-6 text-[var(--accent)]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                        </svg>
                      </div>
                      <h3 className="text-[19px] font-bold text-white tracking-[-0.02em] mb-2 font-['Manrope',system-ui,sans-serif]">
                        {chat("verifyTitle")}
                      </h3>
                      <p className="text-[14px] text-[var(--muted)] tracking-[-0.01em] mb-6 leading-[1.6]">
                        {chat("verifySub")}
                      </p>
                      <div className="flex justify-center">
                        <Turnstile
                          siteKey={process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY!}
                          onSuccess={() => setVerified(true)}
                          options={{ theme: "dark" }}
                        />
                      </div>
                    </div>
                  </div>
                ) : (
                  <ChatSession
                    key={sessionId}
                    initialMessages={restored?.stage === "chat" ? restored.messages ?? [] : []}
                    welcome={welcome}
                    readyToSubmit={readyToSubmit}
                    extractedData={extractedData}
                    prefilterLabel={prefilterLabel}
                    submitError={submitError}
                    onDataExtracted={handleDataExtracted}
                    onMessagesChange={handleMessagesChange}
                    onEdit={handleEdit}
                    onSubmit={() => { handleSubmitBrief(); }}
                  />
                )}
              </>
            )}

            {/* SUBMITTING */}
            {stage === "submitting" && (
              <div className="flex flex-col items-center justify-center min-h-[45vh] text-center">
                <div className="w-12 h-12 rounded-full border-2 border-[var(--border)] border-t-[var(--accent)] animate-spin mb-6" />
                <p className="text-[15px] text-[var(--muted)] tracking-[-0.01em]">
                  {chat("submitting")}
                </p>
              </div>
            )}

            {/* DONE */}
            {stage === "done" && (
              <div className="flex flex-col items-center justify-center min-h-[45vh] text-center">
                <div className="w-16 h-16 rounded-full bg-[var(--accent)]/15 border border-[var(--accent)]/30 flex items-center justify-center mb-6">
                  <svg className="w-8 h-8 text-[var(--accent)]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                </div>
                <h2 className="text-[24px] md:text-[26px] font-bold text-white tracking-[-0.03em] mb-3 font-['Manrope',system-ui,sans-serif]">
                  {chat("doneTitle")}
                </h2>
                <p className="text-[14px] text-[var(--muted)] tracking-[-0.01em] mb-2 leading-[1.6] max-w-md">
                  {chat("doneBody")}
                </p>
                {briefRef && (
                  <p className="text-[13px] text-[var(--accent)] font-medium tracking-[0.05em] mb-7">
                    {chat("reference")} {briefRef}
                  </p>
                )}
                <div className="flex flex-col sm:flex-row gap-3">
                  <a
                    href={`/${locale}/dashboard`}
                    className="px-5 py-3 bg-[var(--accent)] text-white rounded-[12px] text-[14px] font-medium hover:opacity-90 transition-all duration-150 btn-press tracking-[-0.01em]"
                  >
                    {chat("trackPortal")}
                  </a>
                  <button
                    type="button"
                    onClick={restart}
                    className="px-5 py-3 border border-[var(--border)] text-[var(--muted)] rounded-[12px] text-[14px] hover:text-white hover:border-white/25 transition-all duration-150 btn-press tracking-[-0.01em]"
                  >
                    {chat("startAnother")}
                  </button>
                </div>
              </div>
            )}

          </div>
        </div>
      </div>
    </div>
  );
}

/* ─── Data extraction from chat transcript ─── */
function tryExtractData(fullText: string): IntakeData | null {
  const fields: Array<keyof IntakeData> = [
    "name", "company", "email", "phone", "category", "description", "budget", "timeline",
  ];
  const data: Partial<IntakeData> = {};
  for (const f of fields) {
    const match = fullText.match(new RegExp(`${f}\\s*[:：]\\s*([^\\n]+)`, "i"));
    if (match) data[f] = match[1].trim();
  }
  if (!data.name && !data.email && !data.description) return null;
  return data as IntakeData;
}
