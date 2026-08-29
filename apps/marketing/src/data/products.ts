export interface Product {
  name: string;
  tagline: string;
  description: string;
  url: string;
  status: string;
  accent: string;
  gradient: string;
  iconPath?: string;
}

export const PRODUCTS: Product[] = [
  {
    name: "SILKLEARN",
    tagline: "Knowledge infrastructure that keeps compounding",
    description:
      "A knowledge graph platform that ingests your documents, finds what connects them, and builds a map you can actually walk \u2014 not a search result or a summary. Your scattered expertise becomes structured understanding people can follow, question, and build on.",
    url: "https://silklearn.io",
    status: "Active development",
    accent: "var(--accent)",
    gradient: "from-[#6c63ff] to-[#5a52e0]",
    iconPath: "/images/silklearn.svg",
  },
  {
    name: "SILKLABS",
    tagline: "Build your next project with the right team",
    description:
      "A co-founder and team-matching platform with a genome engine that decomposes 36K+ startups into typed atoms \u2014 industry, business model, technology \u2014 to answer what exists, what\u2019s missing, and who should build it. Features an interactive startup ecosystem graph, whitespace analysis, and AI-driven team assembly.",
    url: "https://labs.silkdev.com.tn",
    status: "Active development",
    accent: "#66e3ff",
    gradient: "from-[#00d9ff] to-[#00a8cc]",
    iconPath: "/images/silklabs.avif",
  },
  {
    name: "LucaP",
    tagline: "Modern accounting for the multi-tenant era",
    description:
      "A multi-tenant SaaS accounting platform that merges the accounting power of QuickBooks with the customer convenience of LemonSqueezy. Invoice viewing, payment processing (international + Tunisian local), and comprehensive financial management \u2014 all under one roof.",
    url: "https://nexus.silkdev.io",
    status: "Active development",
    accent: "#f59e0b",
    gradient: "from-[#f59e0b] to-[#d97706]",
    iconPath: "/images/lucap.svg",
  },
  {
    name: "SILKGUILD",
    tagline: "A distributed learning platform on RPG mechanics",
    description:
      "Roadmap.sh meets Discord \u2014 a gamified learning ecosystem built around guilds, bounties, and academies. Learners level up by completing quests, collaborating in guilds, and claiming bounties. Structured skill progression driven by community participation.",
    url: "#",
    status: "Coming soon",
    accent: "#ec4899",
    gradient: "from-[#ec4899] to-[#db2777]",
    iconPath: "/images/silkguild.avif",
  },
  {
    name: "SILKLOOM",
    tagline: "Workflows that weave themselves",
    description:
      "AI workflow agents that run your operational work: describe the workflow once, shuttles execute it with evidence, and every pass weaves the result into reusable memory — work that compounds instead of repeating.",
    url: "#",
    status: "Coming soon",
    accent: "#5eead4",
    gradient: "from-[#5eead4] to-[#2dd4bf]",
    iconPath: "/images/silkloom-logo.png",
  },
  {
    name: "Meridian",
    tagline: "The main line — client portal & agency ops",
    description:
      "The portal that runs the engagement: project planner, AI project representative, lifecycle, and client communication in one visible workspace — every client knows exactly where their project stands.",
    url: "#",
    status: "Coming soon",
    accent: "#34d399",
    gradient: "from-[#34d399] to-[#0ea5e9]",
    iconPath: "/images/meridian-logo.svg",
  },
];
