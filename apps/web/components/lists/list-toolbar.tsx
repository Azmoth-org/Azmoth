"use client"

import { SearchIcon, XIcon } from "lucide-react"
import { usePathname, useRouter, useSearchParams } from "next/navigation"
import * as React from "react"

import { Button } from "@workspace/ui/components/button"
import { Input } from "@workspace/ui/components/input"
import { Label } from "@workspace/ui/components/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
} from "@workspace/ui/components/select"

import { nextHref, type ListParams } from "@/lib/lists/params"

/**
 * The filter controls, and the only client code on either list page.
 *
 * They own no state that describes the list. Every control resolves to a URL and pushes it; the
 * server component above re-runs, re-reads `searchParams` and re-fetches. That is why a filtered list
 * is shareable, survives the back button, and cannot drift from what the table below is showing —
 * a control that also held the value in a `useState` would have two sources of truth, and they would
 * disagree the first time somebody pressed Back.
 *
 * `router.push` rather than `<Link>` for the select, because the select's value is not a place a
 * reader can point at before choosing it. The search box *is* a form, so Enter works, and it pushes
 * on submit rather than on every keystroke: a request per character against an endpoint that returns
 * whole proposals would be a self-inflicted load test, and the filter is an exact match anyway, so
 * there is nothing useful to show after four of the eighteen characters of a case id.
 */

/** One option in the status dropdown. `value` is `null` for "all". */
export type StatusOption = { value: string | null; label: string }

/** The sentinel the select uses for "all", because a `Select` value cannot be null. */
const ALL = "__all__"

export function ListToolbar({
  params,
  statuses,
  search,
}: {
  params: ListParams
  statuses: readonly StatusOption[]
  /**
   * The search field, or nothing. `/padnext/batch/history` has no search: the engine's batch listing
   * filters on `status` and `created_after` and there is no text column to match, so a box that
   * accepted a batch id and silently ignored it would be worse than no box.
   */
  search?: { label: string; placeholder: string; hint?: string }
}) {
  const router = useRouter()
  const pathname = usePathname()
  // Read from the live URL rather than only from `params`, so a Back navigation that changes the
  // query string is reflected here without the server having to hand down new props.
  const live = useSearchParams()
  const [draft, setDraft] = React.useState(params.query ?? "")

  // The URL is authoritative. When it changes underneath this component — Back, a shared link, the
  // reset button — the input follows it instead of holding whatever was last typed.
  const urlQuery = live.get("q") ?? ""
  const [syncedTo, setSyncedTo] = React.useState(urlQuery)
  if (urlQuery !== syncedTo) {
    setSyncedTo(urlQuery)
    setDraft(urlQuery)
  }

  const selected = params.status ?? ALL
  const filtered = params.status !== null || (params.query ?? "") !== ""

  function go(patch: Partial<ListParams>) {
    router.push(nextHref(pathname, params, patch))
  }

  return (
    <div className="flex flex-wrap items-end gap-3">
      <div className="space-y-2">
        <Label htmlFor="status-filter">Status</Label>
        <Select
          value={selected}
          onValueChange={(value) => {
            if (typeof value !== "string") return
            go({ status: value === ALL ? null : value })
          }}
        >
          {/*
            The label is rendered from the controlled value rather than through `<SelectValue />`.
            The primitive resolves its label on the client only, so the server render — and therefore
            the first paint, and therefore a shared link — would show the raw `DRAFT` instead of
            "Entwurf". The same reason `components/review/case-selector.tsx` does it this way.
          */}
          <SelectTrigger id="status-filter" className="w-48">
            <span className="flex-1 text-left">
              {statuses.find((option) => (option.value ?? ALL) === selected)?.label ?? "Alle"}
            </span>
          </SelectTrigger>
          <SelectContent>
            {statuses.map((option) => (
              <SelectItem key={option.value ?? ALL} value={option.value ?? ALL}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {search ? (
        <form
          className="space-y-2"
          onSubmit={(event) => {
            event.preventDefault()
            const trimmed = draft.trim()
            go({ query: trimmed.length > 0 ? trimmed : null })
          }}
        >
          <Label htmlFor="list-search">{search.label}</Label>
          <div className="flex items-center gap-2">
            <Input
              id="list-search"
              name="q"
              type="search"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              placeholder={search.placeholder}
              // `search` inputs get a native clear affordance in some browsers; clearing it and
              // submitting is what removes the filter, which is why the submit handler treats an
              // empty value as "no filter" rather than as "match the empty string".
              className="w-64"
              aria-describedby={search.hint ? "list-search-hint" : undefined}
            />
            <Button type="submit" variant="outline">
              <SearchIcon aria-hidden />
              Suchen
            </Button>
          </div>
          {search.hint ? (
            <p id="list-search-hint" className="text-muted-foreground text-xs">
              {search.hint}
            </p>
          ) : null}
        </form>
      ) : null}

      {filtered ? (
        <Button
          type="button"
          variant="ghost"
          onClick={() => router.push(pathname)}
          // Not disabled when unfiltered — it is absent, so there is no dead control to reason about.
        >
          <XIcon aria-hidden />
          Filter zurücksetzen
        </Button>
      ) : null}
    </div>
  )
}
