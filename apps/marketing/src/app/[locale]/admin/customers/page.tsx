import { getSession } from "@/lib/session";
import prisma from "@/lib/prisma";
import { redirect } from "next/navigation";
import { isAdmin } from "@/lib/admin";
import { resolveUserSlug } from "@/lib/slug";
import { Building2 } from "lucide-react";
import { CustomersTable, type AdminCustomerRow } from "@/components/agency/CustomersTable";

export default async function CustomersPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const session = await getSession();
  const { locale } = await params;
  if (!session) redirect(`/${locale}/login`);
  if (!isAdmin(session)) {
    redirect(`/${locale}/client/${await resolveUserSlug(session.user.id, session.user.email)}`);
  }

  const customers = await prisma.customer.findMany({
    include: {
      user: {
        select: {
          email: true,
          slug: true,
          projects: {
            select: { status: true, phase: true, updatedAt: true },
            orderBy: { updatedAt: "desc" },
          },
        },
      },
    },
    orderBy: { updatedAt: "desc" },
  });

  const rows: AdminCustomerRow[] = customers.map((c) => {
    const projects = c.user?.projects ?? [];
    const active = projects.filter(
      (p) => p.phase !== "completed" && p.status !== "completed"
    ).length;
    const lastActivity = projects[0]?.updatedAt ?? c.updatedAt;
    return {
      id: c.id,
      name: c.companyName || c.displayName,
      displayName: c.displayName,
      company: c.companyName,
      email: c.primaryEmail ?? c.user?.email ?? null,
      phone: c.primaryPhone,
      taxId: c.taxIdentifier,
      projects: projects.length,
      active,
      lastActivity: lastActivity.toISOString(),
      portalSlug: c.user?.slug ?? null,
    };
  });

  return (
    <div className="bg-[var(--background)]">
      <div className="mx-auto max-w-7xl">
        <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-2xl md:text-3xl font-bold tracking-[-0.03em] font-['Manrope',system-ui,sans-serif] text-foreground">
              Customers
            </h1>
            <p className="text-sm text-muted-foreground mt-0.5">
              Billable clients — contacts, addresses and tax identifiers for invoicing.
            </p>
          </div>
          <span className="px-3 py-1 rounded-full text-xs font-medium bg-white/10 text-muted-foreground">
            {customers.length} customers
          </span>
        </div>

        {customers.length === 0 ? (
          <div className="bg-[var(--surface)] border border-[var(--border)] rounded-2xl p-12 text-center">
            <Building2 className="mx-auto mb-3 size-8 text-muted-foreground/50" />
            <p className="text-muted-foreground">No customers yet — seed demo clients or create profiles for your first projects.</p>
          </div>
        ) : (
          <CustomersTable customers={rows} />
        )}
      </div>
    </div>
  );
}
