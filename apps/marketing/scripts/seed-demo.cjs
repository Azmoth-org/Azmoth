/* Demo customers + projects seed for the agency console (local + prod).
   Run with DATABASE_URL set:  node scripts/seed-demo.cjs
   Idempotent (upserts on stable ids). */
const { PrismaClient } = require("@prisma/client");
const { PrismaPg } = require("@prisma/adapter-pg");

const adapter = new PrismaPg({ connectionString: process.env.DATABASE_URL });
const prisma = new PrismaClient({ adapter });

const STAGE_TITLES = {
  web: ["Discovery", "Design", "Development", "Testing", "Launch"],
  ai: ["Use-case mapping", "Data ingestion", "Model fine-tuning", "Integration", "Launch"],
  product: ["Vision & scope", "Architecture", "Build", "Beta", "Launch"],
  crm: ["Discovery", "Design", "Development", "Integration", "Launch"],
};

const CUSTOMERS = [
  {
    id: "customer-demo-ips",
    user: { email: "contact@ips-tunisie.com", name: "Youssef Ben Ali", slug: "ips" },
    customer: {
      displayName: "Youssef Ben Ali",
      title: "Mr",
      givenName: "Youssef",
      familyName: "Ben Ali",
      companyName: "IPS Tunisie",
      primaryEmail: "contact@ips-tunisie.com",
      alternateEmail: "y.benali@ips-tunisie.com",
      primaryPhone: "+216 71 234 567",
      mobile: "+216 98 112 233",
      webAddress: "https://ips-tunisie.com",
      taxIdentifier: "MF 1624321T",
      billingAddress: { line1: "Avenue Habib Bourguiba 12", city: "Tunis", state: "Tunis", postalCode: "1001", country: "Tunisia" },
      notes: "Long-term client — renews annually. Invoices payable 30 days.",
    },
    projects: [
      {
        id: "project-demo-ips",
        name: "IPS Platform",
        category: "web",
        status: "in_progress",
        phase: "in_progress",
        quote: { lineItems: [{ label: "Design", amount: 4000 }, { label: "Development", amount: 9000 }], total: 13000, currency: "TND", depositPercent: 50, depositAmount: 6500 },
        paymentStatus: "partial",
        stages: [0, 1, 2],
        tasks: ["Design system tokens", "Service catalog pages", "Booking flow wireframes", "API integration", "SEO + meta audit"],
      },
    ],
  },
  {
    id: "customer-demo-wolves",
    user: { email: "wolves@gym.tn", name: "Karim Haddad", slug: "wolves-gym" },
    customer: {
      displayName: "Karim Haddad",
      title: "Mr",
      givenName: "Karim",
      familyName: "Haddad",
      companyName: "Wolves Gym",
      primaryEmail: "wolves@gym.tn",
      primaryPhone: "+216 72 555 890",
      mobile: "+216 50 777 321",
      webAddress: "https://wolvesgym.tn",
      taxIdentifier: "MF 1789552A",
      billingAddress: { line1: "Route de la Corniche 8", city: "Bizerte", state: "Bizerte", postalCode: "7000", country: "Tunisia" },
      notes: "Wants a member dashboard with attendance tracking.",
    },
    projects: [
      {
        id: "project-demo-wolves",
        name: "Wolves Gym Membership Site",
        category: "web",
        status: "proposed",
        phase: "quoting",
        quote: { lineItems: [{ label: "Website", amount: 3500 }, { label: "Booking module", amount: 1500 }], total: 5000, currency: "TND", depositPercent: 50, depositAmount: 2500 },
        paymentStatus: "unpaid",
        stages: [0],
        tasks: ["Membership pricing page", "Booking flow", "Stripe test mode"],
      },
    ],
  },
  {
    id: "customer-demo-podomus",
    user: { email: "hello@podomus.tn", name: "Sana Mejri", slug: "podomus" },
    customer: {
      displayName: "Sana Mejri",
      title: "Ms",
      givenName: "Sana",
      familyName: "Mejri",
      companyName: "Podomus SARL",
      primaryEmail: "hello@podomus.tn",
      primaryPhone: "+216 71 899 100",
      webAddress: "https://podomus.tn",
      taxIdentifier: "MF 1543328H",
      billingAddress: { line1: "Rue du Lac Malaren 4", city: "Les Berges du Lac", state: "Tunis", postalCode: "1053", country: "Tunisia" },
      notes: "Delivered. Potential follow-up: mobile app.",
    },
    projects: [
      {
        id: "project-demo-podomus",
        name: "Podomus Landing + CRM",
        category: "crm",
        status: "completed",
        phase: "completed",
        quote: { lineItems: [{ label: "Landing", amount: 2200 }, { label: "CRM integration", amount: 1800 }], total: 4000, currency: "TND", depositPercent: 100, depositAmount: 4000 },
        paymentStatus: "paid",
        stages: [0, 1, 2, 3, 4],
        tasks: ["Landing copy + sections", "HubSpot-style CRM sync", "Contact forms", "Analytics wiring"],
      },
    ],
  },
  {
    id: "customer-demo-lucap",
    user: { email: "ops@lucap.tn", name: "Amine Trabelsi", slug: "lucap" },
    customer: {
      displayName: "Amine Trabelsi",
      title: "Dr",
      givenName: "Amine",
      familyName: "Trabelsi",
      companyName: "LucaP",
      primaryEmail: "ops@lucap.tn",
      primaryPhone: "+216 22 444 555",
      webAddress: "https://lucap.tn",
      taxIdentifier: "MF 1488220N",
      billingAddress: { line1: "Immeuble Le Printemps, Bureau 3", city: "Sousse", state: "Sousse", postalCode: "4000", country: "Tunisia" },
      notes: "Product client — quarterly invoicing.",
    },
    projects: [
      {
        id: "project-demo-lucap",
        name: "LucaP Accounting Suite",
        category: "product",
        status: "in_progress",
        phase: "in_progress",
        quote: { lineItems: [{ label: "Phase 1", amount: 12000 }, { label: "Phase 2", amount: 18000 }], total: 30000, currency: "TND", depositPercent: 40, depositAmount: 12000 },
        paymentStatus: "partial",
        stages: [0, 1, 2],
        tasks: ["Chart of accounts", "Invoice generation", "Multi-tenant isolation", "Reports v1"],
      },
    ],
  },
  {
    id: "customer-demo-meridian",
    user: { email: "contact@meridian-services.tn", name: "Omar Gharbi", slug: "meridian" },
    customer: {
      displayName: "Omar Gharbi",
      title: "Mr",
      givenName: "Omar",
      familyName: "Gharbi",
      companyName: "Meridian Services",
      primaryEmail: "contact@meridian-services.tn",
      primaryPhone: "+216 70 123 456",
      webAddress: "https://meridian-services.tn",
      taxIdentifier: "MF 1699004K",
      billingAddress: { line1: "Zone touristique, BP 45", city: "Hammamet", state: "Nabeul", postalCode: "8050", country: "Tunisia" },
      notes: "",
    },
    projects: [
      {
        id: "project-demo-meridian",
        name: "Meridian Client Portal",
        category: "product",
        status: "launched",
        phase: "delivery_review",
        quote: { lineItems: [{ label: "Portal build", amount: 15000 }], total: 15000, currency: "TND", depositPercent: 50, depositAmount: 7500 },
        paymentStatus: "partial",
        stages: [0, 1, 2, 3],
        tasks: ["Role-based dashboards", "Chat workflow", "Payment link (Konnect)", "Launch checklist"],
      },
    ],
  },
  {
    id: "customer-demo-bigtalk",
    user: { email: "sarra@bigtalk.tn", name: "Sarra Mansouri", slug: "bigtalk" },
    customer: {
      displayName: "Sarra Mansouri",
      title: "Ms",
      givenName: "Sarra",
      familyName: "Mansouri",
      companyName: "BigTalk Communication",
      primaryEmail: "sarra@bigtalk.tn",
      primaryPhone: "+216 71 456 789",
      webAddress: "https://bigtalk.tn",
      taxIdentifier: "MF 1877446B",
      billingAddress: { line1: "Rue de Marseille 22", city: "Tunis", state: "Tunis", postalCode: "1002", country: "Tunisia" },
      notes: "Referred by IPS. Wants an AI support agent demo.",
    },
    projects: [
      {
        id: "project-demo-bigtalk",
        name: "BigTalk AI Support Agent",
        category: "ai",
        status: "proposed",
        phase: "admin_review",
        quote: null,
        paymentStatus: null,
        stages: [0],
        tasks: ["Docs inventory", "Tone samples"],
      },
    ],
  },
];

(async () => {
  for (const entry of CUSTOMERS) {
    // Portal account
    const user = await prisma.user.upsert({
      where: { email: entry.user.email },
      update: { name: entry.user.name, slug: entry.user.slug, role: "user" },
      create: { email: entry.user.email, name: entry.user.name, slug: entry.user.slug, role: "user", emailVerified: true },
    });

    // Billing profile
    await prisma.customer.upsert({
      where: { id: entry.id },
      update: { ...entry.customer, userId: user.id },
      create: { id: entry.id, ...entry.customer, userId: user.id },
    });

    for (const p of entry.projects) {
      const brief = await prisma.brief.upsert({
        where: { id: `${p.id}-brief` },
        update: {},
        create: {
          id: `${p.id}-brief`,
          userId: user.id,
          name: entry.customer.companyName || entry.customer.displayName,
          email: entry.customer.primaryEmail,
          category: p.category,
          description: p.tasks.join(", "),
          status: "promoted",
        },
      });

      const project = await prisma.project.upsert({
        where: { id: p.id },
        update: { userId: user.id, briefId: brief.id, phase: p.phase, status: p.status, quote: p.quote, paymentStatus: p.paymentStatus },
        create: {
          id: p.id,
          userId: user.id,
          briefId: brief.id,
          name: p.name,
          category: p.category,
          status: p.status,
          phase: p.phase,
          quote: p.quote,
          paymentStatus: p.paymentStatus,
        },
      });

      const titles = STAGE_TITLES[p.category] || STAGE_TITLES.web;
      for (let i = 0; i < titles.length; i++) {
        const status = i < p.stages.length - 1 ? "done" : i === p.stages.length - 1 ? "in_progress" : "pending";
        await prisma.stage.upsert({
          where: { id: `${p.id}-stage-${i}` },
          update: { status, title: titles[i], order: i },
          create: { id: `${p.id}-stage-${i}`, projectId: p.id, key: titles[i].toLowerCase().replace(/\s+/g, "_"), title: titles[i], order: i, status },
        });
      }

      const statuses = ["pending", "in_progress", "review", "done"];
      for (let i = 0; i < p.tasks.length; i++) {
        // spread tasks across statuses so the kanban has content in every column
        const status = p.status === "completed" ? "done" : statuses[i % statuses.length];
        await prisma.task.upsert({
          where: { id: `${p.id}-task-${i}` },
          update: { title: p.tasks[i], status, order: i },
          create: { id: `${p.id}-task-${i}`, projectId: p.id, title: p.tasks[i], status, order: i },
        });
      }
    }
  }

  // One fresh brief in the inbox for the demo
  await prisma.brief.upsert({
    where: { id: "brief-demo-inbox" },
    update: {},
    create: {
      id: "brief-demo-inbox",
      name: "NartaQ",
      email: "hello@nartaq.tn",
      category: "web",
      description: "Logistics platform: fleet tracking dashboard and a client booking portal.",
      scope: "Fleet dashboard, booking portal, API",
      status: "received",
    },
  });

  console.log(`Seeded ${CUSTOMERS.length} demo customers.`);
  await prisma.$disconnect();
})();
