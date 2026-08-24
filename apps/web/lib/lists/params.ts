/**
 * The URL *is* the list state, and this module is the only thing that knows its spelling.
 *
 * Both list pages keep their filters and their page number in the query string — `?status=DRAFT&page=2`
 * — rather than in React state, and that is a decision with three consequences worth naming:
 *
 * * **A filtered list is shareable.** "The 14 rejected drafts" is a link a reviewer can paste into a
 *   ticket, and it survives a reload, a back button and a bookmark. State held in a `useState` is
 *   none of those things.
 * * **The fetch stays on the server.** The page reads `searchParams`, calls the engine from the
 *   server component, and `ENGINE_BASE_URL` never reaches the browser — the rule every other engine
 *   call in this app follows. The only client code is the three controls that push a new URL.
 * * **There is one source of truth.** A control that pushed a URL *and* set local state would have
 *   two, and they would disagree the first time somebody used the back button.
 *
 * `page` is 1-based and `offset` is not in the URL at all. The engine's contract is `limit`/`offset`,
 * but a human pasting a link reads "page 2"; deriving the offset here means the wire format and the
 * shareable format can differ without either one leaking.
 *
 * Every parser below is total: any query string, however malformed, resolves to a valid request. A
 * `?page=-4` or `?page=abc` renders page 1 rather than a 500, because a URL is user input and this
 * one arrives from a paste as often as from a click.
 */

/**
 * Rows per page, fixed rather than a control.
 *
 * The engine caps `limit` at 100, so a selector would offer a choice between 50 and 100 — and a
 * proposal row in that response carries its whole `solver_result`, so doubling it doubles a payload
 * that is already the largest read in the application, to render a table of text. Not worth a
 * control. The figure travels in the pagination row so a reader can still see what a page is.
 */
export const PAGE_SIZE = 50

/** What both pages read out of the URL. `query` is only meaningful on `/proposals`. */
export type ListParams = {
  page: number
  status: string | null
  query: string | null
}

/**
 * Next hands `searchParams` as `string | string[] | undefined` per key, because `?page=1&page=2` is a
 * legal URL. The first value wins — arbitrary, but deterministic, which is what matters for a
 * paginated read where the alternative is a different page on every request.
 */
export type RawSearchParams = Record<string, string | string[] | undefined>

function first(raw: RawSearchParams, key: string): string | null {
  const value = raw[key]
  const single = Array.isArray(value) ? value[0] : value
  if (typeof single !== "string") return null
  const trimmed = single.trim()
  return trimmed.length > 0 ? trimmed : null
}

/**
 * A page number from the URL, or 1.
 *
 * Clamped at the bottom but **not** at the top, because the total is not known until the engine has
 * answered. A page past the end therefore renders as a stated "this page is empty" rather than being
 * silently rewritten to the last page — silently moving somebody to a different page than the URL
 * they followed is worse than telling them the URL is stale.
 */
function parsePage(raw: RawSearchParams): number {
  const value = first(raw, "page")
  if (value === null) return 1
  const parsed = Number.parseInt(value, 10)
  return Number.isFinite(parsed) && parsed >= 1 ? parsed : 1
}

/**
 * A status from the URL, if it is one this list offers.
 *
 * Validated against the page's own options rather than passed through. An unrecognised value would
 * otherwise reach the engine and come back as a `422` — a filter typo rendering as "Prüfungen konnten
 * nicht geladen werden" is a bad trade for a query string somebody hand-edited.
 */
function parseStatus(raw: RawSearchParams, allowed: readonly string[]): string | null {
  const value = first(raw, "status")
  if (value === null) return null
  const upper = value.toUpperCase()
  return allowed.includes(upper) ? upper : null
}

export function readListParams(
  raw: RawSearchParams,
  { statuses }: { statuses: readonly string[] },
): ListParams {
  return {
    page: parsePage(raw),
    status: parseStatus(raw, statuses),
    query: first(raw, "q"),
  }
}

/** `page` → the engine's `offset`. */
export function offsetOf(page: number): number {
  return (page - 1) * PAGE_SIZE
}

/**
 * How many pages `total` rows make. Never zero: an empty list is page 1 of 1, not page 1 of 0.
 *
 * "Seite 1 von 0" is the kind of line that makes a reader distrust every other number on the screen.
 */
export function pageCount(total: number): number {
  if (!Number.isFinite(total) || total <= 0) return 1
  return Math.max(1, Math.ceil(total / PAGE_SIZE))
}

/**
 * The engine query string for one page of a list.
 *
 * `status` and the case filter are only appended when set, so a default view asks for
 * `?limit=50&offset=0` and nothing else — the engine treats an absent filter and an empty one
 * identically, but a URL that says what it means is easier to read in a log.
 */
export function engineQuery({
  page,
  status,
  caseId,
}: {
  page: number
  status: string | null
  caseId?: string | null
}): string {
  const search = new URLSearchParams({
    limit: String(PAGE_SIZE),
    offset: String(offsetOf(page)),
  })
  if (status) search.set("status", status)
  if (caseId) search.set("case_id", caseId)
  return search.toString()
}

/**
 * Build the next browser URL from the current one plus a patch.
 *
 * Two rules are enforced here rather than at each call site, because getting either wrong is a defect
 * a reader would blame on the data:
 *
 * * **A changed filter resets to page 1.** Staying on page 4 while narrowing 900 rows to 12 lands on
 *   an empty page, and the reader concludes the filter matched nothing.
 * * **A default is absent, not explicit.** `page=1` and an empty `status` are dropped, so the
 *   unfiltered list is `/proposals` and not `/proposals?page=1&status=&q=`. It keeps a shared link
 *   short and makes "am I filtered?" answerable by looking at the address bar.
 */
export function nextHref(
  pathname: string,
  current: ListParams,
  patch: Partial<ListParams>,
): string {
  const merged: ListParams = { ...current, ...patch }
  const filterChanged =
    (patch.status !== undefined && patch.status !== current.status) ||
    (patch.query !== undefined && patch.query !== current.query)
  const page = patch.page !== undefined ? patch.page : filterChanged ? 1 : merged.page

  const search = new URLSearchParams()
  if (merged.status) search.set("status", merged.status)
  if (merged.query) search.set("q", merged.query)
  if (page > 1) search.set("page", String(page))

  const qs = search.toString()
  return qs.length > 0 ? `${pathname}?${qs}` : pathname
}

/**
 * Whether a search term is a proposal handle rather than a case id.
 *
 * It exists because of a gap the search box cannot close on its own: the engine's list endpoint
 * filters on `case_id` and has no `proposal_id` parameter, so a pasted `prop_…` matches nothing and
 * the empty state would read as "no such proposal" when it means "this list cannot search for that".
 * Recognising the shape lets the empty state say which of the two happened. See the note in
 * `components/proposals/proposals-table.tsx`.
 */
export function looksLikeProposalId(value: string): boolean {
  return /^prop_[0-9a-f]{4,}$/i.test(value.trim())
}
