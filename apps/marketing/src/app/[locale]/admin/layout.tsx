import { PortalLayout } from "@/components/portal/PortalLayout";

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return <PortalLayout>{children}</PortalLayout>;
}
