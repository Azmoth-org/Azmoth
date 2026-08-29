/**
 * Project lifecycle — the client-facing state machine.
 *
 * intake → admin_review → quoting → payment → in_progress → iteration ⇄ delivery_review → completed
 *
 * - intake: the AI collects/confirms the specs until complete, then flags the
 *   project for review.
 * - admin_review: an admin is in the conversation — client chat is disabled,
 *   the admin's message shows with their name/avatar, and the admin releases
 *   control when done.
 * - quoting: admin turns the confirmed specs into a final quote (line items,
 *   total, deposit). Saved quote → payment.
 * - payment: the client pays the deposit/full amount in-chat (Konnect).
 * - in_progress: stages/tasks track delivery; the client can interject at any
 *   time (request modification → iteration) until they confirm the delivery.
 * - delivery_review: client confirms the final delivery → completed.
 */

export const PROJECT_PHASES = [
  "intake",
  "admin_review",
  "quoting",
  "payment",
  "in_progress",
  "iteration",
  "delivery_review",
  "completed",
] as const;

export type ProjectPhase = (typeof PROJECT_PHASES)[number];

/** Client chat is off only while an admin is actively in the conversation. */
export function canUserChat(phase: string | null | undefined): boolean {
  return phase !== "admin_review";
}

/** True for phases where the client is waiting on the studio. */
export function isWaitingOnStudio(phase: string | null | undefined): boolean {
  return phase === "quoting" || phase === "payment";
}

export function isTerminal(phase: string | null | undefined): boolean {
  return phase === "completed";
}

export const PHASE_LABELS: Record<ProjectPhase, string> = {
  intake: "Specs intake",
  admin_review: "Studio review",
  quoting: "Preparing your quote",
  payment: "Awaiting payment",
  in_progress: "In progress",
  iteration: "Iterating with you",
  delivery_review: "Confirming delivery",
  completed: "Completed",
};

export const PHASE_LABELS_FR: Record<ProjectPhase, string> = {
  intake: "Collecte des specs",
  admin_review: "Revue studio",
  quoting: "Préparation du devis",
  payment: "En attente de paiement",
  in_progress: "En cours",
  iteration: "Itération avec vous",
  delivery_review: "Confirmation de livraison",
  completed: "Terminé",
};

export function phaseLabel(phase: string | null | undefined, locale: string): string {
  const map = locale === "fr" ? PHASE_LABELS_FR : PHASE_LABELS;
  return (map[phase as ProjectPhase] ?? phase) || "intake";
}

/* ─────────────────────────────────────────────────────────────
 * Admin board — the full thought → deliverable lifecycle.
 * Ideation is the briefs column; project columns group phases.
 * ───────────────────────────────────────────────────────────── */

export type BoardColumn = {
  key: string;
  title: string;
  hint?: string;
  phases?: ProjectPhase[];
};

export const BOARD_COLUMNS: BoardColumn[] = [
  { key: "ideation", title: "Ideation", hint: "client thoughts" },
  { key: "intake", title: "Specs", phases: ["intake"] },
  { key: "admin_review", title: "Studio review", phases: ["admin_review"] },
  { key: "quoting", title: "Quoting", phases: ["quoting"] },
  { key: "payment", title: "Payment", phases: ["payment"] },
  { key: "in_progress", title: "In progress", phases: ["in_progress", "iteration"] },
  { key: "delivery_review", title: "Delivery review", phases: ["delivery_review"] },
  { key: "completed", title: "Completed", phases: ["completed"] },
];

/** The board column a project phase belongs to (defaults to the first project column). */
export function boardColumnForPhase(phase: string | null | undefined): BoardColumn {
  return (
    BOARD_COLUMNS.find((c) => c.phases?.includes(phase as ProjectPhase)) ??
    BOARD_COLUMNS[1]
  );
}

/** The phase a project moves to when stepping right on the board. */
export function nextPhase(phase: string | null | undefined): string {
  const idx = BOARD_COLUMNS.findIndex((c) => c.phases?.includes(phase as ProjectPhase));
  for (let i = idx + 1; i < BOARD_COLUMNS.length; i++) {
    if (BOARD_COLUMNS[i].phases?.length) return BOARD_COLUMNS[i].phases![0];
  }
  return phase ?? "intake";
}

/** The phase a project moves to when stepping left on the board. */
export function prevPhase(phase: string | null | undefined): string {
  const idx = BOARD_COLUMNS.findIndex((c) => c.phases?.includes(phase as ProjectPhase));
  for (let i = idx - 1; i > 0; i--) {
    if (BOARD_COLUMNS[i].phases?.length) return BOARD_COLUMNS[i].phases![0];
  }
  return phase ?? "intake";
}
