"use client";

import { useEffect, useState } from "react";
import { useRouter, useParams } from "next/navigation";
import { useLocale } from "next-intl";
import { Link } from "@/i18n/navigation";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { ProjectTimeline } from "@/components/portal/ProjectTimeline";
import TasksPanel from "@/components/portal/TasksPanel";
import { ProjectPanel } from "@/components/portal/ProjectPanel";
import { ArrowLeft, Calendar, CheckCircle2, ClipboardList, MessageSquare, Sparkles } from "lucide-react";

type Brief = {
  id: string;
  name: string | null;
  email: string | null;
  category: string | null;
  description: string | null;
  scope: string | null;
  createdAt: string;
} | null;
type Stage = {
  id: string;
  key: string;
  title: string | null;
  status: string;
  order: number;
  startedAt: string | null;
  completedAt: string | null;
};
type Task = { id: string; title: string; status: string; order: number };
type Project = {
  id: string;
  name: string | null;
  category: string | null;
  status: string;
  brief: Brief;
  stages: Stage[];
  tasks: Task[];
};

export default function ClientProjectPage() {
  const router = useRouter();
  const params = useParams<{ id: string; slug: string }>();
  const locale = useLocale();
  const [project, setProject] = useState<Project | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`/api/projects/${params.id}`, { cache: "no-store" })
      .then(async (r) => {
        if (r.status === 401 || r.status === 403) {
          router.push(`/${locale}/login`);
          return null;
        }
        if (!r.ok) return null;
        const d = await r.json();
        return d.project ?? null;
      })
      .then((p) => {
        setProject(p);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [params.id, locale, router]);

  if (loading) {
    return (
      <div className="min-h-screen bg-[var(--background)] pt-32">
        <div className="mx-auto max-w-6xl px-4 text-sm text-muted-foreground">Loading project…</div>
      </div>
    );
  }

  if (!project) {
    return (
      <div className="min-h-screen bg-[var(--background)] pt-32">
        <div className="mx-auto max-w-6xl px-4">
          <p className="mb-6 text-sm text-muted-foreground">Project not found.</p>
          <Button asChild variant="link" className="px-0">
            <Link href={`/client/${params.slug}`}>← Back to your projects</Link>
          </Button>
        </div>
      </div>
    );
  }

  const doneStages = project.stages.filter((s) => s.status === "done").length;
  const progress = project.stages.length ? Math.round((doneStages / project.stages.length) * 100) : 0;

  return (
    <div className="bg-[var(--background)]">
      <div className="mx-auto max-w-6xl">
        {/* Back + header */}
        <Button asChild variant="ghost" className="mb-6 px-0 text-sm text-muted-foreground">
          <Link href={`/client/${params.slug}`}>
            <ArrowLeft className="size-4" />
            My projects
          </Link>
        </Button>

        <div className="mb-8 flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <span className="rounded-full bg-[var(--accent)]/10 px-3 py-1 text-xs font-medium text-[var(--accent)]">
                {project.category ?? "Project"}
              </span>
              <span className="rounded-full border border-[var(--border)] px-3 py-1 text-xs capitalize text-muted-foreground">
                {project.status.replace("_", " ")}
              </span>
            </div>
            <h1 className="text-3xl md:text-4xl font-bold tracking-[-0.03em] text-foreground">
              {project.name ?? "Untitled project"}
            </h1>
            <p className="mt-2 flex items-center gap-1.5 text-sm text-muted-foreground">
              <Calendar className="size-4" />
              {progress}% through the pipeline
            </p>
          </div>

          <div className="w-40">
            <div className="mb-1.5 flex justify-between text-xs text-muted-foreground">
              <span>Progress</span>
              <span>{progress}%</span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-[var(--surface)]">
              <div className="h-full rounded-full bg-[var(--accent)] transition-all duration-500" style={{ width: `${progress}%` }} />
            </div>
            <p className="mt-2 flex items-center gap-1.5 text-xs text-muted-foreground">
              <CheckCircle2 className="size-3.5" />
              {doneStages}/{project.stages.length} stages · {project.tasks.filter((t) => t.status === "done").length}/{project.tasks.length} tasks
            </p>
          </div>
        </div>

        {/* Tabs */}
        <Tabs defaultValue="overview" className="mb-8">
          <TabsList>
            <TabsTrigger value="overview">
              <Sparkles className="size-3.5" />
              Overview
            </TabsTrigger>
            <TabsTrigger value="plan">
              <ClipboardList className="size-3.5" />
              Planner
            </TabsTrigger>
            <TabsTrigger value="chat">
              <MessageSquare className="size-3.5" />
              Chat with your rep
            </TabsTrigger>
          </TabsList>

          <TabsContent value="overview" className="mt-6">
            <div className="grid gap-6 lg:grid-cols-5">
              <Card className="lg:col-span-3">
                <CardHeader>
                  <CardTitle>Brief</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-[15px] leading-relaxed text-muted-foreground">
                    {project.brief?.description || "No brief description on file."}
                  </p>
                  {project.brief?.scope && (
                    <p className="mt-4 text-sm text-muted-foreground">
                      <span className="font-medium text-foreground">Scope:</span> {project.brief.scope}
                    </p>
                  )}
                </CardContent>
              </Card>
              <Card className="lg:col-span-2">
                <CardHeader>
                  <CardTitle>Pipeline</CardTitle>
                </CardHeader>
                <CardContent>
                  <ul className="space-y-2.5">
                    {project.stages.map((s) => (
                      <li key={s.id} className="flex items-center gap-2.5 text-sm">
                        <span
                          className={`h-2 w-2 rounded-full ${
                            s.status === "done"
                              ? "bg-emerald-500"
                              : s.status === "in_progress" || s.status === "review"
                                ? "bg-[var(--accent)]"
                                : "bg-[var(--border)]"
                          }`}
                        />
                        <span className="flex-1 text-foreground">{s.title ?? s.key}</span>
                        <span className="text-xs capitalize text-muted-foreground">
                          {s.status.replace("_", " ")}
                        </span>
                      </li>
                    ))}
                  </ul>
                </CardContent>
              </Card>
            </div>
          </TabsContent>

          <TabsContent value="plan" className="mt-6 space-y-8">
            <Card>
              <CardHeader>
                <CardTitle>Milestones</CardTitle>
              </CardHeader>
              <CardContent>
                <ProjectTimeline project={project} />
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <TasksPanel projectId={project.id} />
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="chat" className="mt-6">
            <ProjectPanel projectId={project.id} projectName={project.name ?? "this project"} />
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
