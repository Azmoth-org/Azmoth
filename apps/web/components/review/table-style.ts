/**
 * The class strings both position tables share.
 *
 * They were duplicated — including their reasoning — in `accepted-positions-table.tsx` and
 * `blocked-positions-table.tsx`, which is exactly the pair that must not drift: the two tables sit
 * side by side, and a header row that is uppercase in one and not the other reads as two documents.
 */

/**
 * Flush the table to the card's edges and keep the text off them.
 *
 * `CardContent` is given `px-0` by the caller so the header row and the zebra stripes run the full
 * width of the card — a stripe that stops short of the edge reads as a box inside a box. The row
 * padding is restored on the first and last cell instead of on the container.
 */
export const EDGE_PADDING =
  "[&_td:first-child]:pl-6 [&_td:last-child]:pr-6 [&_th:first-child]:pl-6 [&_th:last-child]:pr-6"

/**
 * Column headers: 12px, uppercase, tracked out, muted.
 *
 * `TableHead` ships `text-foreground` at the body's own size, which puts the header on exactly the
 * same visual level as the data under it — so on a screen holding two tables, four prose panels and
 * a hero figure, the one line whose entire job is to say "this column is money" competed with the
 * money. Small caps at low contrast is the cheapest way to make a header read as a *label* rather
 * than as a first row, and it costs the data nothing.
 */
export const HEAD =
  "text-muted-foreground h-10 text-xs font-medium tracking-[0.05em] uppercase"

/** The same, right-aligned, for the figure columns. */
export const HEAD_FIGURE = `${HEAD} px-2 text-right`

/**
 * Side padding for the figure columns.
 *
 * `p-3` on each of Punkte, Faktor and Betrag spent 72px of a 730px table on whitespace between
 * numbers that are already right-aligned and therefore already separated. That width belongs to the
 * Leistung column, which is a sentence.
 */
export const FIGURE = "px-2 text-right align-middle tabular-nums"

/**
 * 56px, as a floor rather than a fixed height.
 *
 * `h-14` on a `tr` is a minimum — a row whose Leistung wraps to two lines or carries a "Begründung
 * fehlt" badge grows past it, which is correct. What it buys is that the *short* rows stop being
 * 40px: a table of nine positions at 40px is a block of text, and the same nine at 56px is a list
 * a reader's eye can step down.
 */
export const ROW = "h-14"

/**
 * German medical legend text needs to be allowed to break.
 *
 * "Elektrokardiographische" is twenty-three characters that no amount of column-width negotiation
 * will shorten: without this the longest single word in a cell becomes that column's minimum width,
 * and the table overflows its card at every viewport. `hyphens-auto` does the right thing because
 * the document is `lang="de"`; `break-words` is the fallback for the strings that have no hyphen
 * points, such as a rule id.
 */
export const WRAP = "hyphens-auto break-words"

/**
 * Two lines of a GOÄ legend, and no more — on screen.
 *
 * The official texts run from four words to forty, and a table whose row height is set by its
 * longest legend is a table nobody scans. Two lines is enough to tell the positions apart, which is
 * what the column is for here; the full sentence is one hover (or one tap on the row) away.
 *
 * `print:line-clamp-none` is not a nicety. A printed proposal is the document a physician signs and
 * a Rechnungsprüfer disputes, and a legend cut off at "…" in ink cannot be checked against the
 * catalog. Paper has no hover, so paper gets the whole sentence.
 */
export const CLAMP_2 = "line-clamp-2 print:line-clamp-none"

/**
 * The desktop table and the card list are the same data twice, and exactly one of them may ever be
 * on screen — or on paper. The table is the printed form: a stack of cards would waste most of a
 * sheet and lose the column alignment that makes an invoice checkable.
 *
 * The switch is at `lg`, not `md`. A tablet at 834px still shows the navigation rail, which leaves
 * the accepted table roughly 550px for six columns — enough that it renders, not enough that it
 * fits, so the Betrag column ended up behind a horizontal scrollbar. An amount you have to swipe to
 * see is worse than an amount in a card.
 */
export const TABLE_ONLY = "hidden lg:block print:block"
export const CARDS_ONLY = "lg:hidden print:hidden"
