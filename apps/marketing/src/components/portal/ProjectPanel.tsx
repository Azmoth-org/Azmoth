"use client";

import { useCallback, useEffect, useState } from "react";
import { useLocale } from "next-intl";
import { useRouter } from "next/navigation";
import {
  BadgeDollarSign,
  CheckCircle2,
  FileUp,
  Lock,
  MessageSquareWarning,
  Paperclip,
  RefreshCw,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { phaseLabel, PROJECT_PHASES } from "@/lib/projectLifecycle";
import ProjectChat from "@/components/portal/ProjectChat";

type HistoryMessage = {
  id: string;
  role: string;
  senderName?: string | null;
  content: string;
  createdAt: string;
};

type Quote = {
  lineItems: { label: string; amount: number; qty: number }[];
  total: number;
  currency: string;
  depositPercent: number;
  depositAmount: number;
};

type ProjectFile = { pathname: string; url: string; size: number; uploadedAt: string };

const PHASE_TONE: Record<string, string> = {
  intake: "bg-[var(--accent)]/10 text-[var(--accent)] border-[var(--accent)]/20",
  admin_review: "bg-amber-500/10 text-amber-400 border-amber-500/20",
  quoting: "bg-sky-500/10 text-sky-400 border-sky-500/20",
  payment: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
  in_progress: "bg-[var(--accent)]/10 text-[var(--accent)] border-[var(--accent)]/20",
  iteration: "bg-purple-500/10 text-purple-400 border-purple-500/20",
  delivery_review: "bg-amber-500/10 text-amber-400 border-amber-500/20",
  completed: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
};

/**
 * Project lifecycle panel: phase banner, quote + in-chat payment, iteration
 * / delivery actions, file uploads — wrapped around the project chat.
 */
export function ProjectPanel({ projectId, projectName }: { projectId: string; projectName: string }) {
  const locale = useLocale();
  const router = useRouter();
  const [phase, setPhase] = useState<string>("intake");
  const [quote, setQuote] = useState<Quote | null>(null);
  const [chatDisabled, setChatDisabled] = useState(false);
  const [history, setHistory] = useState<HistoryMessage[]>([]);
  const [files, setFiles] = useState<ProjectFile[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState("");

  const refresh = useCallback(async () => {
    const res = await fetch(`/api/projects/${projectId}/admin/messages`);
    if (!res.ok) return;
    const data = await res.json();
    setPhase(data.phase ?? "intake");
    setQuote(data.quote ?? null);
    setChatDisabled(!!data.chatDisabled);
    setHistory(data.messages ?? []);
  }, [projectId]);

  useEffect(() => {
    refresh();
    fetch(`/api/projects/${projectId}/files`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => d?.files && setFiles(d.files));
  }, [refresh, projectId]);

  const run = async (label: string, fn: () => Promise<Response>) => {
    setBusy(label);
    setNotice("");
    const res = await fn();
    const data = await res.json().catch(() => ({}));
    if (!res.ok) setNotice(data?.error ?? "Something went wrong");
    else {
      if (data?.phase) setPhase(data.phase);
      if (data?.payUrl) window.location.href = data.payUrl;
      setNotice("");
    }
    setBusy(null);
  };

  const pay = () =>
    run("pay", () =>
      fetch(`/api/projects/${projectId}/payments`, { method: "POST" }),
    );

  const lifecycle = (action: "modification" | "delivery") =>
    run(action, () =>
      fetch(`/api/projects/${projectId}/lifecycle`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action }),
      }),
    );

  const onUpload = async (file: File) => {
    setBusy("upload");
    setNotice("");
    const res = await fetch(`/api/projects/${projectId}/files?filename=${encodeURIComponent(file.name)}`, {
      method: "POST",
      body: file,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) setNotice(data?.error ?? "Upload failed");
    else {
      setFiles((prev) => [...prev, { pathname: data.pathname, url: data.url, size: 0, uploadedAt: "" }]);
      setNotice("");
    }
    setBusy(null);
  };

  const showPay = phase === "payment" && quote && quote.depositAmount > 0;
  const showLifecycle = ["in_progress", "iteration", "delivery_review"].includes(phase);

  return (
    <div className="space-y-4">
      {/* Phase banner */}
      <div className="flex flex-wrap items-center gap-3">
        <span className={`rounded-full border px-3 py-1 text-xs font-medium ${PHASE_TONE[phase] ?? PHASE_TONE.intake}`}>
          {phaseLabel(phase, locale)}
        </span>
        {chatDisabled && (
          <span className="flex items-center gap-1.5 rounded-full border border-amber-500/20 bg-amber-500/10 px-3 py-1 text-xs text-amber-400">
            <Lock className="size-3" /> The studio is in the conversation — chat paused
          </span>
        )}
      </div>

      {notice && <p className="text-sm text-red-400">{notice}</p>}

      {/* Quote + payment */}
      {showPay && quote && (
        <Card className="border-emerald-500/20 bg-emerald-500/5">
          <CardContent className="pt-6">
            <div className="mb-3 flex items-center gap-2">
              <BadgeDollarSign className="size-4 text-emerald-400" />
              <h3 className="font-semibold text-foreground">Your quote is ready</h3>
            </div>
            <ul className="mb-4 space-y-1.5">
              {quote.lineItems.map((li, i) => (
                <li key={i} className="flex justify-between text-sm text-muted-foreground">
                  <span>
                    {li.label}
                    {li.qty > 1 ? ` ×${li.qty}` : ""}
                  </span>
                  <span className="text-foreground">
                    {(li.amount * li.qty).toFixed(2)} {quote.currency}
                  </span>
                </li>
              ))}
              <li className="flex justify-between border-t border-[var(--border)] pt-2 text-sm font-semibold text-foreground">
                <span>Total</span>
                <span>
                  {quote.total.toFixed(2)} {quote.currency}
                </span>
              </li>
            </ul>
            <Button onClick={pay} disabled={busy !== null} className="w-full">
              <BadgeDollarSign className="size-4" />
              {busy === "pay" ? "Opening payment…" : `Pay deposit (${quote.depositAmount.toFixed(2)} ${quote.currency})`}
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Lifecycle actions */}
      {showLifecycle && (
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" onClick={() => lifecycle("modification")} disabled={busy !== null}>
            <RefreshCw className="size-4" />
            {busy === "modification" ? "Opening…" : "Request changes"}
          </Button>
          <Button onClick={() => lifecycle("delivery")} disabled={busy !== null}>
            <CheckCircle2 className="size-4" />
            {busy === "delivery" ? "Confirming…" : "Confirm final delivery"}
          </Button>
        </div>
      )}

      {/* Files */}
      <Card>
        <CardContent className="pt-6">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="flex items-center gap-2 text-sm font-semibold text-foreground">
              <Paperclip className="size-4 text-muted-foreground" /> Files
            </h3>
            <label className="cursor-pointer">
              <input
                type="file"
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) onUpload(f);
                  e.target.value = "";
                }}
              />
              <Button variant="outline" size="sm" disabled={busy !== null} asChild={false} type="button">
                <FileUp className="size-3.5" />
                {busy === "upload" ? "Uploading…" : "Upload"}
              </Button>
            </label>
          </div>
          {files.length === 0 ? (
            <p className="text-sm text-muted-foreground">No files yet — attach specs, screenshots, documents.</p>
          ) : (
            <ul className="space-y-1.5">
              {files.map((f) => (
                <li key={f.pathname}>
                  <a
                    href={`/api/projects/${projectId}/files?pathname=${encodeURIComponent(f.pathname)}`}
                    className="text-sm text-[var(--accent)] hover:underline"
                  >
                    {f.pathname.split("/").pop()}
                  </a>
                  {f.size > 0 && (
                    <span className="ml-2 text-xs text-muted-foreground">
                      {(f.size / 1024).toFixed(0)} KB
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      {/* Chat (paused while the studio is in the conversation) */}
      {chatDisabled ? (
        <div className="flex h-40 items-center justify-center gap-2 rounded-2xl border border-[var(--border)] bg-[var(--surface)] text-sm text-muted-foreground">
          <MessageSquareWarning className="size-4" />
          Chat paused while the studio reviews — it reopens when they hand it back.
        </div>
      ) : (
        <ProjectChat projectId={projectId} projectName={projectName} history={history} />
      )}
    </div>
  );
}
