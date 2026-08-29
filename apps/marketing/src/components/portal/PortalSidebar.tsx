"use client";

import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ChevronsUpDown, FolderKanban, LayoutDashboard, LogOut, Moon, ShieldCheck, Sun, Users } from "lucide-react";
import { Link, useRouter } from "@/i18n/navigation";
import { authClient, useSession } from "@/lib/auth-client";
import { slugFromEmail } from "@/lib/slugify";
import { useTheme } from "@/lib/theme";

/** Client-portal slug for the sidebar — DB slug if the session carries it, else email-derived. */
function clientSlugFor(user: { email?: string | null; slug?: string | null } | null | undefined): string {
  return user?.slug || slugFromEmail(user?.email || "");
}

/** SILKDEV portal sidebar (shadcn dashboard-01 block structure), role-aware:
 *  admins lead with the Agency console, clients get their own portal home. */
export function PortalSidebar() {
  const { data: session } = useSession();
  const router = useRouter();
  const user = session?.user;
  const isAdmin = user?.role === "admin";
  const clientSlug = clientSlugFor(user);
  const { theme, toggle } = useTheme();

  const handleSignOut = async () => {
    await authClient.signOut();
    router.push("/login");
  };

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton size="lg" asChild>
              <Link href={isAdmin ? "/admin" : `/client/${clientSlug}`}>
                <div className="flex aspect-square size-8 items-center justify-center rounded-lg bg-foreground/10">
                  <img src="/favicon.svg" alt="" className="size-5" />
                </div>
                <div className="grid flex-1 text-left text-sm leading-tight">
                  <span className="truncate font-semibold text-foreground">SILKDEV</span>
                  <span className="truncate text-xs text-muted-foreground">
                    {isAdmin ? "Agency" : "Client portal"}
                  </span>
                </div>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Portal</SidebarGroupLabel>
          <SidebarMenu>
            {isAdmin ? (
              <>
                <SidebarMenuItem>
                  <SidebarMenuButton asChild>
                    <Link href="/admin">
                      <ShieldCheck />
                      <span>Agency console</span>
                    </Link>
                  </SidebarMenuButton>
                </SidebarMenuItem>
                <SidebarMenuItem>
                  <SidebarMenuButton asChild>
                    <Link href="/admin/projects">
                      <FolderKanban />
                      <span>Projects</span>
                    </Link>
                  </SidebarMenuButton>
                </SidebarMenuItem>
                <SidebarMenuItem>
                  <SidebarMenuButton asChild>
                    <Link href="/admin/customers">
                      <Users />
                      <span>Customers</span>
                    </Link>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              </>
            ) : (
              <SidebarMenuItem>
                <SidebarMenuButton asChild>
                  <Link href={`/client/${clientSlug}`}>
                    <LayoutDashboard />
                    <span>Dashboard</span>
                  </Link>
                </SidebarMenuButton>
              </SidebarMenuItem>
            )}
          </SidebarMenu>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter>
        <SidebarMenu>
          <SidebarMenuItem>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <SidebarMenuButton
                  size="lg"
                  className="data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground"
                >
                  <div className="flex aspect-square size-8 items-center justify-center rounded-lg bg-foreground/10 text-sm font-semibold text-foreground">
                    {(user?.name || "U").charAt(0).toUpperCase()}
                  </div>
                  <div className="grid flex-1 text-left text-sm leading-tight">
                    <span className="truncate font-semibold text-foreground">
                      {user?.name || "Account"}
                    </span>
                    <span className="truncate text-xs text-muted-foreground">{user?.email}</span>
                  </div>
                  <ChevronsUpDown className="ml-auto size-4 text-muted-foreground" />
                </SidebarMenuButton>
              </DropdownMenuTrigger>
              <DropdownMenuContent side="top" align="end" className="w-[--radix-dropdown-menu-trigger-width] min-w-56 rounded-lg">
                <DropdownMenuLabel className="p-0 font-normal">
                  <div className="flex items-center gap-2 px-1 py-1.5 text-left text-sm">
                    <div className="grid flex-1 text-left text-sm leading-tight">
                      <span className="truncate font-semibold text-foreground">{user?.name}</span>
                      <span className="truncate text-xs text-muted-foreground">{user?.email}</span>
                    </div>
                  </div>
                </DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={toggle} className="gap-2">
                  {theme === "light" ? <Moon className="size-4" /> : <Sun className="size-4" />}
                  {theme === "light" ? "Dark mode" : "Light mode"}
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={handleSignOut} className="gap-2">
                  <LogOut className="size-4" />
                  Sign out
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
    </Sidebar>
  );
}
