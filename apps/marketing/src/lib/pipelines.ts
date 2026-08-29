export type StageTemplate = {
  key: string;
  title: string;
};

export type PipelineTemplate = {
  key: string;
  label: string;
  stages: StageTemplate[];
};

/**
 * Delivery pipeline templates per predefined service category.
 * The intake chat prefilter uses these category values:
 *   web-app | mobile-app | ai-agent | fractional-cto | design | other
 */
export const PIPELINE_TEMPLATES: Record<string, PipelineTemplate> = {
  "web-app": {
    key: "web-app",
    label: "Website / Web App",
    stages: [
      { key: "discovery", title: "Discovery & Scope" },
      { key: "design", title: "Design" },
      { key: "development", title: "Development" },
      { key: "qa", title: "QA & Testing" },
      { key: "launch", title: "Launch & Handoff" },
    ],
  },
  "mobile-app": {
    key: "mobile-app",
    label: "Mobile App",
    stages: [
      { key: "discovery", title: "Discovery & Scope" },
      { key: "prototype", title: "Prototype" },
      { key: "design", title: "Design" },
      { key: "development", title: "Development" },
      { key: "store-submission", title: "Store Submission" },
      { key: "launch", title: "Launch & Handoff" },
    ],
  },
  "ai-agent": {
    key: "ai-agent",
    label: "AI / Agent Pipeline",
    stages: [
      { key: "discovery", title: "Discovery & Scope" },
      { key: "data-audit", title: "Data & Tooling Audit" },
      { key: "architecture", title: "Agent Architecture" },
      { key: "build", title: "Agent Build" },
      { key: "evals", title: "Evaluation & Hardening" },
      { key: "deploy", title: "Deploy & Monitor" },
    ],
  },
  "fractional-cto": {
    key: "fractional-cto",
    label: "Fractional CTO",
    stages: [
      { key: "audit", title: "Tech & Team Audit" },
      { key: "roadmap", title: "Roadmap & Strategy" },
      { key: "execution", title: "Execution & Hiring" },
      { key: "review", title: "Quarterly Review" },
    ],
  },
  design: {
    key: "design",
    label: "Design / UI-UX",
    stages: [
      { key: "discovery", title: "Discovery & Brand" },
      { key: "wireframes", title: "Wireframes" },
      { key: "ui-design", title: "UI Design" },
      { key: "prototype", title: "Interactive Prototype" },
      { key: "handoff", title: "Handoff" },
    ],
  },
  other: {
    key: "other",
    label: "Custom Project",
    stages: [
      { key: "discovery", title: "Discovery & Scope" },
      { key: "proposal", title: "Proposal & Approval" },
      { key: "design", title: "Design" },
      { key: "development", title: "Development" },
      { key: "qa", title: "QA & Testing" },
      { key: "launch", title: "Launch & Handoff" },
    ],
  },
};

export function getPipelineTemplate(category: string | null | undefined): PipelineTemplate {
  if (category && PIPELINE_TEMPLATES[category]) {
    return PIPELINE_TEMPLATES[category];
  }
  return PIPELINE_TEMPLATES.other;
}
