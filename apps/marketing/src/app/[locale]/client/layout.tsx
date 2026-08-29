import { PortalLayout } from "@/components/portal/PortalLayout";

export default function ClientLayout({ children }: { children: React.ReactNode }) {
  return <PortalLayout>{children}</PortalLayout>;
}
