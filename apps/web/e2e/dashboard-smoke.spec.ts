import { expect, test, type Page } from "@playwright/test"

/**
 * The one end-to-end test: dashboard → a stored proposal.
 *
 * ## What this is for
 *
 * `turbo lint typecheck build` proves the frontend compiles. It proves nothing about whether the
 * screen a reader lands on still renders, or whether the row they click still leads anywhere — and
 * those are exactly the regressions that ship silently, because a broken `Suspense` boundary, a
 * card that throws into an error state and a link whose `?id=` stopped being read all typecheck
 * perfectly. This walks the path instead of type-checking it.
 *
 * Deliberately one test and deliberately shallow. It asserts that the dashboard renders, that the
 * "Letzte Prüfungen" card is in one of the two states it is allowed to be in, and — when there is
 * something to click — that clicking a row opens that proposal. It does not test approval, batch
 * upload, exports or the rule queue. When one of those breaks, this test should still pass; that is
 * the point of a tripwire.
 *
 * ## Running it
 *
 * ```sh
 * # 1. the engine, from apps/engine (Soufflé and Clingo must be on PATH)
 * python -m uvicorn app.main:app --port 8000
 *
 * # 2. the tests, from apps/web — the dev server starts itself if it is not already up
 * pnpm test:e2e
 * ```
 *
 * Or against the whole containerised stack, which brings up both:
 *
 * ```sh
 * docker compose -f infra/docker/docker-compose.yml up --build
 * pnpm --filter web test:e2e
 * ```
 *
 * **The engine is not optional.** Every figure on the dashboard is fetched server-side, so with the
 * engine down the page renders three cards that say so — cleanly, which is the problem: the run
 * would go green having verified that the error states work. The first assertion below detects that
 * and fails with the reason, so a missing backend never reads as a passing smoke test.
 */

/** The system health card's title. Anchored, so the "Der Systemstatus …" error text cannot match. */
const SYSTEM_STATUS = /^Systemstatus/

/** What the health card renders instead when `callEngine` could not reach the engine. */
const ENGINE_UNREACHABLE = "Engine nicht erreichbar"

/** Every row of the "Letzte Prüfungen" card is a link carrying the proposal's id. */
const PROPOSAL_ROW = 'a[href^="/review?id="]'

/** The card's empty state on a database that has never solved anything. */
const NO_PROPOSALS = "Noch keine Prüfungen vorhanden"

test("Übersicht lädt und eine Prüfung lässt sich öffnen", async ({ page }) => {
  // ---------------------------------------------------------------------------------------------
  // 1. The dashboard renders.
  // ---------------------------------------------------------------------------------------------
  await page.goto("/")

  await expect(
    page.getByRole("heading", { name: "Übersicht", level: 1 })
  ).toBeVisible()

  await assertEngineIsUp(page)

  // The system health card resolved. It is inside its own `Suspense` boundary, so this is also the
  // assertion that streaming still works — a skeleton that never resolves fails here.
  await expect(page.getByText(SYSTEM_STATUS).first()).toBeVisible()

  // ---------------------------------------------------------------------------------------------
  // 2. The "Letzte Prüfungen" card resolved into one of its two legitimate states.
  //
  // Which one depends on the database, and both are correct — a fresh checkout has solved nothing.
  // Waiting for "a row OR the empty state" rather than asserting one of them is what keeps this
  // test from depending on fixtures it does not create.
  // ---------------------------------------------------------------------------------------------
  await expect(page.getByText("Letzte Prüfungen")).toBeVisible()

  const rows = page.locator(PROPOSAL_ROW)
  const emptyState = page.getByText(NO_PROPOSALS)

  await expect(rows.first().or(emptyState)).toBeVisible()

  if (await emptyState.isVisible()) {
    // Nothing stored yet. The card says so in words rather than rendering an empty box, and there
    // is no row to follow — so the flow ends here, passing.
    test.info().annotations.push({
      type: "info",
      description: `Keine Prüfungen in der Datenbank — Leerzustand geprüft, kein Zeilen-Klick.`,
    })
    return
  }

  // ---------------------------------------------------------------------------------------------
  // 3. The first row opens its proposal.
  //
  // The id is read off the link before clicking, so the assertion afterwards is that *this* record
  // opened — not merely that some review screen rendered. That distinction is the whole content of
  // the deep-link fix this test guards: the rows carried `?id=` for a while before `/review` read
  // it, and a test that only checked the destination page would have passed throughout.
  // ---------------------------------------------------------------------------------------------
  const firstRow = rows.first()
  const href = await firstRow.getAttribute("href")
  const proposalId = new URL(href ?? "", "http://localhost").searchParams.get(
    "id"
  )

  expect(
    proposalId,
    `Die erste Zeile trägt keine Vorschlags-ID: href=${href}`
  ).toBeTruthy()

  await firstRow.click()

  await expect(page).toHaveURL(new RegExp(`/review\\?id=${proposalId}`))
  await expect(
    page.getByRole("heading", {
      name: "GOÄ-Abrechnungsvorschlag prüfen",
      level: 1,
    })
  ).toBeVisible()

  // The proposal itself arrived, not just the shell. `ProposalHeader` renders the id through
  // `CopyableHash` with `length={32}`, and a `prop_<16 hex>` handle is 21 characters — so it is
  // shown whole and can be asserted on directly.
  await expect(
    page.getByText(proposalId!, { exact: true }).first()
  ).toBeVisible()
})

/**
 * Fail with the reason, rather than with a locator timeout, when the engine is not running.
 *
 * Without this the run dies twenty seconds later on "Systemstatus" not being visible, which reads
 * like a UI regression and sends the reader to `git log` instead of to a terminal.
 */
async function assertEngineIsUp(page: Page): Promise<void> {
  const unreachable = page.getByText(ENGINE_UNREACHABLE)
  const healthy = page.getByText(SYSTEM_STATUS).first()

  await expect(healthy.or(unreachable).first()).toBeVisible()

  expect(
    await unreachable.isVisible(),
    "Die Engine ist nicht erreichbar — die Übersicht rendert nur ihre Fehlerzustände. " +
      "Engine starten (Standard http://localhost:8000, siehe ENGINE_BASE_URL) und erneut laufen lassen."
  ).toBe(false)
}
