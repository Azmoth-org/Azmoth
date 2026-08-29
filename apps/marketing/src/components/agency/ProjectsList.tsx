"use client";

import { ProjectsTable, type AdminProjectRow } from "@/components/agency/ProjectsTable";
import { StageList, type StageItem } from "@/components/agency/StageList";
import { useAdminProjectActions } from "@/components/agency/useAdminProjectActions";

type ProjectsListProject = {
  id: string;
  name: string | null;
  category: string | null;
  status: string;
  phase: string;
  createdAt: string | Date;
  stages: StageItem[];
  user: { name: string | null; email: string | null; slug: string | null } | null;
};

/** Standalone projects table (search/filter/expand) for /admin/projects. */
export function ProjectsList({ projects }: { projects: ProjectsListProject[] }) {
  const { busyId, setProject, setStage, addStage, deleteStage } = useAdminProjectActions();

  const rows: AdminProjectRow[] = projects.map((project) => {
    const doneCount = project.stages.filter((st) => st.status === "done").length;
    const pct = project.stages.length ? Math.round((doneCount / project.stages.length) * 100) : 0;
    return {
      id: project.id,
      name: project.name || project.category || project.id,
      category: project.category,
      clientEmail: project.user?.email ?? null,
      phase: project.phase,
      status: project.status,
      progress: pct,
      createdAt: project.createdAt.toString(),
      renderExpanded: () => (
        <StageList
          stages={project.stages}
          projectId={project.id}
          busyId={busyId}
          onSetStatus={setStage}
          onDelete={deleteStage}
          onAdd={addStage}
        />
      ),
    };
  });

  return <ProjectsTable projects={rows} onStatusChange={setProject} />;
}
