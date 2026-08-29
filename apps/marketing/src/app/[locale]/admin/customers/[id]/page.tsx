import { getSession } from "@/lib/session";
import prisma from "@/lib/prisma";
import { redirect } from "next/navigation";
import { isAdmin } from "@/lib/admin";
import { resolveUserSlug } from "@/lib/slug";
import { CustomerDetail } from "@/components/agency/CustomerDetail";

export default async function CustomerDetailPage({
  params,
}: {
  params: Promise<{ locale: string; id: string }>;
}) {
  const session = await getSession();
  const { locale, id } = await params;
  if (!session) redirect(`/${locale}/login`);
  if (!isAdmin(session)) {
    redirect(`/${locale}/client/${await resolveUserSlug(session.user.id, session.user.email)}`);
  }

  const customer = await prisma.customer.findUnique({
    where: { id },
    include: {
      user: {
        select: {
          id: true,
          name: true,
          email: true,
          slug: true,
          projects: {
            include: { stages: { orderBy: { order: "asc" } } },
            orderBy: { updatedAt: "desc" },
          },
        },
      },
    },
  });

  if (!customer) redirect(`/${locale}/admin/customers`);

  return <CustomerDetail customer={customer} />;
}
