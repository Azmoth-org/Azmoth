"use client";

import { useMemo } from "react";
import { createColumnHelper } from "@tanstack/react-table";
import { FolderKanban, MessageSquare, MoreHorizontal, UserRound } from "lucide-react";
import { Link } from "@/i18n/navigation";
import { useDataTable } from "@/hooks/use-data-table";
import { DataTable } from "@/components/data-table/data-table";
import { DataTableToolbar } from "@/components/data-table/data-table-toolbar";
import { DataTableFacetedFilter } from "@/components/data-table/data-table-faceted-filter";
import { DataTableColumnHeader } from "@/components/data-table/data-table-column-header";
import { DataTablePagination } from "@/components/data-table/data-table-pagination";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

export type AdminCustomerRow = {
  id: string;
  name: string; // company || displayName
  displayName: string;
  company: string | null;
  email: string | null;
  phone: string | null;
  taxId: string | null;
  projects: number;
  active: number;
  lastActivity: string; // ISO
  portalSlug: string | null;
};

const columnHelper = createColumnHelper<AdminCustomerRow>();

const ACTIVITY_OPTIONS = [
  { label: "Has active work", value: "active" },
  { label: "No active work", value: "idle" },
];

const TAX_OPTIONS = [
  { label: "Business (MF)", value: "business" },
  { label: "Individual", value: "individual" },
];

export function CustomersTable({ customers }: { customers: AdminCustomerRow[] }) {
  const columns = useMemo(
    () => [
      columnHelper.accessor("name", {
        header: ({ column }) => <DataTableColumnHeader column={column} label="Customer" />,
        cell: ({ row }) => (
          <div className="flex min-w-0 items-center gap-2.5">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[var(--accent)]/10 text-xs font-semibold text-[var(--accent)]">
              {row.original.name.charAt(0).toUpperCase()}
            </div>
            <div className="min-w-0">
              <p className="truncate font-medium text-foreground">{row.original.name}</p>
              {row.original.company && row.original.displayName !== row.original.name && (
                <p className="truncate text-xs text-muted-foreground">{row.original.displayName}</p>
              )}
            </div>
          </div>
        ),
        enableSorting: true,
        enableColumnFilter: false,
        enableGlobalFilter: true,
      }),
      columnHelper.accessor("email", {
        header: ({ column }) => <DataTableColumnHeader column={column} label="Contact" />,
        cell: ({ row }) => (
          <div className="min-w-0">
            <p className="truncate text-sm text-foreground">{row.original.email || "—"}</p>
            {row.original.phone && <p className="truncate text-xs text-muted-foreground">{row.original.phone}</p>}
          </div>
        ),
        enableSorting: true,
        enableColumnFilter: false,
        enableGlobalFilter: true,
      }),
      columnHelper.accessor("taxId", {
        header: ({ column }) => <DataTableColumnHeader column={column} label="Tax ID" />,
        cell: ({ row }) =>
          row.original.taxId ? (
            <Badge variant="outline" className="border-[var(--border)] text-muted-foreground">
              {row.original.taxId}
            </Badge>
          ) : (
            <span className="text-xs text-muted-foreground/60">—</span>
          ),
        enableSorting: false,
        enableColumnFilter: false,
        enableGlobalFilter: true,
      }),
      columnHelper.accessor("projects", {
        header: ({ column }) => <DataTableColumnHeader column={column} label="Projects" />,
        cell: ({ row }) => <span className="text-sm text-foreground">{row.original.projects}</span>,
        enableSorting: true,
        enableColumnFilter: false,
      }),
      columnHelper.accessor("lastActivity", {
        header: ({ column }) => <DataTableColumnHeader column={column} label="Last activity" />,
        cell: ({ row }) => (
          <span className="text-xs text-muted-foreground">
            {new Date(row.original.lastActivity).toLocaleDateString()}
          </span>
        ),
        enableSorting: true,
        enableColumnFilter: false,
      }),
      // Derived faceted column — the accessor value IS the filter value.
      columnHelper.accessor((row) => (row.active > 0 ? "active" : "idle"), {
        id: "activity",
        header: ({ column }) => <DataTableColumnHeader column={column} label="Activity" />,
        cell: ({ getValue }) =>
          getValue() === "active" ? (
            <span className="text-xs font-medium text-[var(--accent)]">Active</span>
          ) : (
            <span className="text-xs text-muted-foreground/60">Idle</span>
          ),
        enableSorting: false,
        enableColumnFilter: true,
        meta: { options: ACTIVITY_OPTIONS },
      }),
      // Hidden faceted column for the tax-type filter.
      columnHelper.accessor((row) => (row.taxId ? "business" : "individual"), {
        id: "taxType",
        header: () => null,
        cell: () => null,
        enableSorting: false,
        enableColumnFilter: true,
        enableHiding: true,
        meta: { options: TAX_OPTIONS },
      }),
      columnHelper.display({
        id: "actions",
        header: () => null,
        cell: ({ row }) => (
          <div className="flex justify-end">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon" className="size-8 text-muted-foreground hover:text-foreground">
                  <MoreHorizontal className="size-4" />
                  <span className="sr-only">Actions</span>
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-56">
                <DropdownMenuItem asChild>
                  <Link href={`/admin/customers/${row.original.id}`} className="gap-2">
                    <UserRound className="size-4" />
                    View customer
                  </Link>
                </DropdownMenuItem>
                <DropdownMenuItem asChild>
                  <Link href="/admin/projects" className="gap-2">
                    <FolderKanban className="size-4" />
                    View projects
                  </Link>
                </DropdownMenuItem>
                <DropdownMenuItem
                  asChild
                  disabled={!row.original.portalSlug}
                  title={row.original.portalSlug ? undefined : "No portal account linked"}
                >
                  <Link
                    href={row.original.portalSlug ? `/client/${row.original.portalSlug}` : "#"}
                    className="gap-2"
                    aria-disabled={!row.original.portalSlug}
                  >
                    <MessageSquare className="size-4" />
                    View chats &amp; requests
                  </Link>
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        ),
      }),
    ],
    []
  );

  const { table } = useDataTable({
    data: customers,
    columns,
    pageCount: Math.ceil(customers.length / 10),
    initialState: {
      sorting: [{ id: "lastActivity", desc: true }],
      columnVisibility: { taxType: false },
    },
    enableAdvancedFilter: false,
  });

  return (
    <DataTable table={table} actionBar={<DataTablePagination table={table} />}>
      <DataTableToolbar table={table}>
        <Input
          value={(table.getState().globalFilter as string) ?? ""}
          onChange={(e) => table.setGlobalFilter(e.target.value)}
          placeholder="Search customers…"
          className="h-8 w-52"
        />
        {table.getColumn("activity") && (
          <DataTableFacetedFilter column={table.getColumn("activity")} title="Activity" options={ACTIVITY_OPTIONS} />
        )}
        {table.getColumn("taxType") && (
          <DataTableFacetedFilter column={table.getColumn("taxType")} title="Tax type" options={TAX_OPTIONS} />
        )}
      </DataTableToolbar>
    </DataTable>
  );
}
