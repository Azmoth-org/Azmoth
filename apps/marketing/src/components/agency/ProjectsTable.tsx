"use client";

import { useMemo, useState } from "react";
import { createColumnHelper } from "@tanstack/react-table";
import { ChevronRight } from "lucide-react";
import { Link } from "@/i18n/navigation";
import { useDataTable } from "@/hooks/use-data-table";
import { DataTable } from "@/components/data-table/data-table";
import { DataTableToolbar } from "@/components/data-table/data-table-toolbar";
import { DataTableFacetedFilter } from "@/components/data-table/data-table-faceted-filter";
import { DataTableColumnHeader } from "@/components/data-table/data-table-column-header";
import { DataTablePagination } from "@/components/data-table/data-table-pagination";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { phaseLabel, PROJECT_PHASES } from "@/lib/projectLifecycle";

/** The tanstack RowExpanding feature API (not in the base Row type). */
interface ExpandableRow {
  toggleExpanded: () => void;
  getIsExpanded: () => boolean;
}

export type AdminProjectRow = {
  id: string;
  name: string;
  category: string | null;
  clientEmail: string | null;
  phase: string;
  status: string;
  progress: number;
  createdAt: string;
  renderExpanded?: () => React.ReactNode;
};

const columnHelper = createColumnHelper<AdminProjectRow>();

const PHASE_OPTIONS = PROJECT_PHASES.map((p) => ({ label: phaseLabel(p, "en"), value: p }));

const STATUS_OPTIONS = ["proposed", "approved", "in_progress", "launched", "completed"].map((s) => ({
  label: s.replace("_", " "),
  value: s,
}));

const STATUS_COLORS: Record<string, string> = {
  proposed: "border-[var(--accent)]/30 text-[var(--accent)]",
  approved: "border-emerald-500/30 text-emerald-400",
  in_progress: "border-amber-500/30 text-amber-400",
  launched: "border-sky-500/30 text-sky-400",
  completed: "border-[var(--border)] text-muted-foreground",
};

export function ProjectsTable({
  projects,
  onStatusChange,
}: {
  projects: AdminProjectRow[];
  onStatusChange: (projectId: string, status: string) => void;
}) {
  const [statusBusy, setStatusBusy] = useState<string | null>(null);

  const columns = useMemo(
    () => [
      columnHelper.display({
        id: "expand",
        header: () => null,
        cell: ({ row }) => {
          const expandable = row as unknown as ExpandableRow;
          return (
            <button
              type="button"
              onClick={() => expandable.toggleExpanded()}
              className="flex size-6 items-center justify-center rounded-md text-muted-foreground transition-transform duration-200 hover:bg-[var(--foreground)]/5 hover:text-foreground data-[expanded=true]:rotate-90"
              data-expanded={expandable.getIsExpanded()}
              aria-label="Toggle stages"
            >
              <ChevronRight className="size-4" />
            </button>
          );
        },
      }),
      columnHelper.accessor("name", {
        header: ({ column }) => <DataTableColumnHeader column={column} label="Project" />,
        cell: ({ row }) => (
          <div className="min-w-0">
            <Link
              href={`/admin/projects/${row.original.id}`}
              draggable={false}
              className="inline-block max-w-full truncate font-medium text-foreground transition-colors hover:text-[var(--accent)]"
            >
              {row.original.name}
            </Link>
            <p className="truncate text-xs text-muted-foreground">{row.original.category || "—"}</p>
          </div>
        ),
        enableSorting: true,
        enableColumnFilter: false,
        enableGlobalFilter: true,
      }),
      columnHelper.accessor("clientEmail", {
        header: ({ column }) => <DataTableColumnHeader column={column} label="Client" />,
        cell: ({ row }) => (
          <span className="text-sm text-muted-foreground">{row.original.clientEmail || "—"}</span>
        ),
        enableSorting: true,
        enableColumnFilter: false,
        enableGlobalFilter: true,
      }),
      columnHelper.accessor("phase", {
        header: ({ column }) => <DataTableColumnHeader column={column} label="Phase" />,
        cell: ({ row }) => (
          <Badge variant="outline" className="border-[var(--border)] text-muted-foreground">
            {phaseLabel(row.original.phase, "en")}
          </Badge>
        ),
        enableSorting: true,
        enableColumnFilter: true,
        meta: {
          options: PHASE_OPTIONS,
        },
      }),
      columnHelper.accessor("status", {
        header: ({ column }) => <DataTableColumnHeader column={column} label="Status" />,
        cell: ({ row }) => (
          <select
            value={row.original.status}
            disabled={statusBusy === row.original.id}
            onChange={(e) => {
              setStatusBusy(row.original.id);
              onStatusChange(row.original.id, e.target.value);
              setTimeout(() => setStatusBusy(null), 600);
            }}
            className={`cursor-pointer rounded-md border bg-transparent px-2 py-1 text-xs font-medium outline-none ${STATUS_COLORS[row.original.status] ?? "border-[var(--border)] text-muted-foreground"}`}
          >
            {STATUS_OPTIONS.map((s) => (
              <option key={s.value} value={s.value} className="bg-[var(--surface)] text-foreground">
                {s.label}
              </option>
            ))}
          </select>
        ),
        enableSorting: true,
        enableColumnFilter: true,
        meta: {
          options: STATUS_OPTIONS,
        },
      }),
      columnHelper.accessor("progress", {
        header: ({ column }) => <DataTableColumnHeader column={column} label="Progress" />,
        cell: ({ row }) => (
          <div className="flex items-center gap-2">
            <div className="h-1.5 w-16 overflow-hidden rounded-full bg-[var(--border)]">
              <div
                className="h-full rounded-full bg-[var(--accent)]"
                style={{ width: `${row.original.progress}%` }}
              />
            </div>
            <span className="text-xs text-muted-foreground">{row.original.progress}%</span>
          </div>
        ),
        enableSorting: true,
        enableColumnFilter: false,
      }),
      columnHelper.accessor("createdAt", {
        header: ({ column }) => <DataTableColumnHeader column={column} label="Created" />,
        cell: ({ row }) => (
          <span className="text-xs text-muted-foreground">
            {new Date(row.original.createdAt).toLocaleDateString()}
          </span>
        ),
        enableSorting: true,
        enableColumnFilter: true,
      }),
    ],
    [statusBusy, onStatusChange],
  );

  const { table } = useDataTable({
    data: projects,
    columns,
    pageCount: Math.ceil(projects.length / 10),
    getRowCanExpand: () => true,
    initialState: {
      sorting: [{ id: "createdAt", desc: true }],
    },
    enableAdvancedFilter: false,
  });

  return (
    <DataTable
      table={table}
      actionBar={<DataTablePagination table={table} />}
    >
      <DataTableToolbar table={table}>
        <Input
          value={(table.getState().globalFilter as string) ?? ""}
          onChange={(e) => table.setGlobalFilter(e.target.value)}
          placeholder="Search projects or clients…"
          className="h-8 w-52"
        />
        {table.getColumn("phase") && (
          <DataTableFacetedFilter
            column={table.getColumn("phase")}
            title="Phase"
            options={PHASE_OPTIONS}
          />
        )}
        {table.getColumn("status") && (
          <DataTableFacetedFilter
            column={table.getColumn("status")}
            title="Status"
            options={STATUS_OPTIONS}
          />
        )}
      </DataTableToolbar>
    </DataTable>
  );
}
