import { expect, test, type Page } from "@playwright/test"

/**
 * Layout regressions in the Positionen table, against a mocked audit response.
 *
 * Every other spec in this suite exercises a live engine (see `dashboard-smoke.spec.ts`'s header)
 * because the figures on those screens are the thing worth proving real. This one is different:
 * it is testing CSS — sticky columns, text containment, a load-time scroll position — none of
 * which depends on what the engine computed, only on how the report is laid out once it arrives.
 * Mocking `POST /api/engine/padnext/audit` makes the spec deterministic (a fixed set of positions
 * chosen to exercise the defects this table was rewritten to fix) and independent of Soufflé,
 * Clingo and a running engine, which `playwright.config.ts` does not start.
 *
 * `chromium`'s storage state still signs the page in — every screen is behind Better Auth — so this
 * still needs the `setup` project's account to exist; see `dashboard-smoke.spec.ts`.
 */

const RECHNUNGS_ID = "R-2026-0001"
const ABRECHNUNGSFALL_ID = "F-2026-0001"

/** A `confirmed_wrong` position carrying two verified defects — the case `bucket_reason` embeds
 * raw finding-type codes for, which the primary Bewertung cell must translate rather than show
 * verbatim. */
const POSITION_WRONG = {
  positionsnr: "1",
  rechnungs_id: RECHNUNGS_ID,
  abrechnungsfall_id: ABRECHNUNGSFALL_ID,
  ziffer: "200",
  go: "GOÄ",
  is_analog: false,
  in_catalog: true,
  // Deliberately long and unbreakable-looking, to exercise the two-line clamp and the
  // full-text tooltip rather than a short label that would never need either.
  official_text:
    "Kompressionsverband einer Extremität mit Wickelung, einschließlich Anlegen von Schienenverbänden, Fixationsverbänden und Stützverbänden",
  claimed_faktor: "4.0",
  claimed_amount_eur: "120.00",
  recomputed_amount_eur: "80.00",
  punkte: 200,
  verdict: "chargeable",
  bucket: "confirmed_wrong",
  bucket_reason:
    "Verifizierte Prüfung fehlgeschlagen: padnext_amount_mismatch, padnext_factor_above_maximum.",
  legal_basis: "§ 5 Abs. 1 GOÄ",
  verified_rule_ids: [] as string[],
  advisory_rule_ids: [] as string[],
  accepted_as_claimed: false,
  justification_present: false,
  justification_required: true,
}

/** A `blocked` position — the "neben 200" Regelurteil case, with both a verified and an advisory
 * rule chip, and a long prose `bucket_reason` that must not spill into a neighbouring column. */
const POSITION_BLOCKED = {
  positionsnr: "2",
  rechnungs_id: RECHNUNGS_ID,
  abrechnungsfall_id: ABRECHNUNGSFALL_ID,
  ziffer: "201",
  go: "GOÄ",
  is_analog: false,
  in_catalog: true,
  official_text: "Anlegen eines Stützverbandes",
  claimed_faktor: "2.3",
  claimed_amount_eur: "45.00",
  recomputed_amount_eur: "45.00",
  punkte: 120,
  verdict: "blocked",
  blocked_by: "200",
  bucket: "unconfirmed",
  bucket_reason:
    "Durch die verifizierte Regel 'ziel_man_301_200' theoretisch ausgeschlossen, aber die " +
    "Positionen wurden an unterschiedlichen Leistungsdaten erbracht. Erfordert menschliche Prüfung.",
  legal_basis: "",
  verified_rule_ids: ["ziel_man_301_200"],
  advisory_rule_ids: ["excl_man_5_7"],
  accepted_as_claimed: false,
  justification_present: false,
  justification_required: false,
}

/** A plain `confirmed_fine` position — the case with nothing to say beyond the badge. */
const POSITION_FINE = {
  positionsnr: "3",
  rechnungs_id: RECHNUNGS_ID,
  abrechnungsfall_id: ABRECHNUNGSFALL_ID,
  ziffer: "5",
  go: "GOÄ",
  is_analog: false,
  in_catalog: true,
  official_text: "Beratung",
  claimed_faktor: "2.3",
  claimed_amount_eur: "23.24",
  recomputed_amount_eur: "23.24",
  punkte: 80,
  verdict: "chargeable",
  bucket: "confirmed_fine",
  bucket_reason:
    "Alle anwendbaren Prüfungen bestanden; geprüft gegen verifizierte Regel(n) ziel_man_301_200.",
  legal_basis: "",
  verified_rule_ids: ["ziel_man_301_200"],
  advisory_rule_ids: [] as string[],
  accepted_as_claimed: true,
  justification_present: false,
  justification_required: false,
}

const REPORT = {
  source_name: "demo.padx",
  nachrichtentyp: "PADnext",
  setting: "praxis",
  catalog_version: "2026-01-01",
  receipt_hash: "e2e-fixture-hash-0000000000000000",
  claimed_total_eur: "188.24",
  confirmed_fine_eur: "23.24",
  confirmed_wrong_eur: "120.00",
  unconfirmed_eur: "45.00",
  recomputed_total_eur: "148.24",
  arithmetic_delta_eur: "40.00",
  unpriceable_claimed_eur: "0.00",
  coverage_ratio: 0.76,
  positions: [POSITION_WRONG, POSITION_BLOCKED, POSITION_FINE],
  findings: [],
  pilot_warnings: [] as string[],
}

async function submitMockedAudit(page: Page) {
  await page.route("**/api/engine/padnext/audit", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(REPORT),
    })
  )

  await page.goto("/padnext")
  await page.locator('input[type="file"]').setInputFiles({
    name: "demo.padx",
    mimeType: "application/octet-stream",
    buffer: Buffer.from("synthetic-e2e-fixture"),
  })
  await page
    .getByRole("checkbox", { name: /Ich bestätige, dass diese Datei/ })
    .check()
  await page.getByRole("button", { name: "PADnext-Datei prüfen" }).click()
  await expect(
    page.getByRole("heading", { name: /Positionen \(3\)/ })
  ).toBeVisible()
}

/**
 * The row's text range must not visually reach past where the next *visible* cell starts.
 *
 * "Next" skips a `hidden` Regelurteil/Regeln column below 1680px: `display: none` collapses a
 * `TableHead`/`TableCell` to a zero bounding rect, and comparing against that would fail every row
 * on every narrower width regardless of whether anything actually overlaps.
 */
async function assertNoOverlapWithNextCell(page: Page, testId: string) {
  const overflowing = await page.evaluate((id) => {
    const offenders: string[] = []
    for (const el of Array.from(
      document.querySelectorAll<HTMLElement>(`[data-testid="${id}"]`)
    )) {
      const cell = el.closest("td")
      if (!cell) continue
      let next = cell.nextElementSibling as HTMLElement | null
      while (next && getComputedStyle(next).display === "none") {
        next = next.nextElementSibling as HTMLElement | null
      }
      if (!next) continue
      const range = document.createRange()
      range.selectNodeContents(el)
      const textRight = range.getBoundingClientRect().right
      const nextLeft = next.getBoundingClientRect().left
      if (textRight > nextLeft + 1) {
        offenders.push(`${id}: text right ${textRight} > next cell left ${nextLeft}`)
      }
    }
    return offenders
  }, testId)
  expect(overflowing).toEqual([])
}

const WIDTHS = [1280, 1440, 1680]
const ZOOMS = [1, 1.25, 1.5]

for (const width of WIDTHS) {
  test.describe(`Positionen-Tabelle @ ${width}px`, () => {
    test.use({ viewport: { width, height: 900 } })

    test(`lädt mit scrollLeft 0 und ohne überlappenden Text (${width}px)`, async ({
      page,
    }) => {
      await submitMockedAudit(page)

      const scrollLeft = await page
        .getByTestId("positions-scroll")
        .evaluate((el) => el.scrollLeft)
      expect(scrollLeft).toBe(0)

      for (const zoom of ZOOMS) {
        await page.evaluate((z) => {
          document.documentElement.style.zoom = String(z)
        }, zoom)
        await assertNoOverlapWithNextCell(page, "leistung-text")
        await assertNoOverlapWithNextCell(page, "bewertung-text")
      }
      await page.evaluate(() => {
        document.documentElement.style.zoom = "1"
      })
    })

    test(`erste Spalte bleibt beim horizontalen Scrollen sichtbar (${width}px)`, async ({
      page,
    }) => {
      await submitMockedAudit(page)

      const container = page.getByTestId("positions-scroll")
      const before = await page
        .getByTestId("pos-cell")
        .first()
        .boundingBox()
      await container.evaluate((el) => {
        el.scrollLeft = el.scrollWidth
      })
      const after = await page.getByTestId("pos-cell").first().boundingBox()

      expect(before).not.toBeNull()
      expect(after).not.toBeNull()
      // Sticky, so its position on screen does not move even though the container scrolled.
      expect(after!.x).toBeCloseTo(before!.x, 0)
    })
  })
}

test("Details anzeigen/ausblenden schaltet die Erweiterung um", async ({ page }) => {
  await submitMockedAudit(page)

  const row = page.getByRole("row", { name: /GOÄ 200/ })
  await expect(page.getByTestId("raw-reason-code")).toHaveCount(0)

  await row.getByRole("button", { name: "Details anzeigen" }).click()
  await expect(page.getByTestId("raw-reason-code")).toHaveText(
    "padnext_amount_mismatch, padnext_factor_above_maximum"
  )
  // The primary cell shows the short labels, never the raw codes.
  await expect(page.getByTestId("bewertung-text").first()).not.toContainText(
    "padnext_"
  )

  await row.getByRole("button", { name: "Details ausblenden" }).click()
  await expect(page.getByTestId("raw-reason-code")).toHaveCount(0)
})
