import { expect, test, type Page } from "@playwright/test"

/**
 * Sticky report navigation and metadata visibility on the PADnext audit report.
 *
 * Mocks `POST /api/engine/padnext/audit`, the same way `positionen-table.spec.ts` does — this is
 * independent of a running engine and of what the engine actually computed; it is testing the
 * report's own layout (the nav, the Katalogstand chip), not a figure on screen.
 */

const RECHNUNGS_ID = "R-2026-0002"
const ABRECHNUNGSFALL_ID = "F-2026-0002"

const POSITION = {
  positionsnr: "1",
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

const FINDING = {
  type: "padnext_amount_mismatch",
  severity: "warning",
  positionsnr: "1",
  message: "Der abgerechnete Betrag weicht vom nachgerechneten Betrag ab.",
}

const CATALOG_VERSION = "2026-01-01"

function buildReport(overrides: { findings?: unknown[] }) {
  return {
    source_name: "demo.padx",
    nachrichtentyp: "PADnext",
    setting: "praxis",
    catalog_version: CATALOG_VERSION,
    receipt_hash: "e2e-fixture-hash-nav-0000000000000",
    claimed_total_eur: "23.24",
    confirmed_fine_eur: "23.24",
    confirmed_wrong_eur: "0.00",
    unconfirmed_eur: "0.00",
    recomputed_total_eur: "23.24",
    arithmetic_delta_eur: "0.00",
    unpriceable_claimed_eur: "0.00",
    coverage_ratio: 1,
    positions: [POSITION],
    findings: overrides.findings ?? [],
    pilot_warnings: [] as string[],
  }
}

async function submitMockedAudit(page: Page, report: unknown) {
  await page.route("**/api/engine/padnext/audit", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(report),
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
}

test("Katalogstand ist sichtbar, ohne die Meta-Karte zu öffnen", async ({
  page,
}) => {
  await submitMockedAudit(page, buildReport({ findings: [FINDING] }))
  await expect(
    page.getByText(`Katalogstand ${CATALOG_VERSION}`)
  ).toBeVisible()
})

test("Sticky Nav zeigt Bewertung, Positionen, Befunde, Meta", async ({
  page,
}) => {
  await submitMockedAudit(page, buildReport({ findings: [FINDING] }))
  const nav = page.getByRole("navigation", { name: "Abschnitte dieser Prüfung" })
  await expect(nav).toBeVisible()
  for (const label of ["Bewertung", "Positionen", "Befunde", "Meta"]) {
    await expect(nav.getByRole("link", { name: label })).toBeVisible()
  }
})

test("Befunde fehlt in der Nav, wenn der Bericht keine Befunde hat", async ({
  page,
}) => {
  await submitMockedAudit(page, buildReport({ findings: [] }))
  const nav = page.getByRole("navigation", { name: "Abschnitte dieser Prüfung" })
  await expect(nav).toBeVisible()
  await expect(nav.getByRole("link", { name: "Befunde" })).toHaveCount(0)
  await expect(nav.getByRole("link", { name: "Meta" })).toBeVisible()
})

test("Nav-Links zeigen auf die tatsächlichen Abschnitte der Seite", async ({
  page,
}) => {
  await submitMockedAudit(page, buildReport({ findings: [FINDING] }))
  const nav = page.getByRole("navigation", { name: "Abschnitte dieser Prüfung" })

  const targets: Record<string, string> = {
    Bewertung: "padnext-buckets-heading",
    Positionen: "padnext-positions-heading",
    Befunde: "padnext-findings-heading",
    Meta: "padnext-meta-heading",
  }
  for (const [label, id] of Object.entries(targets)) {
    await expect(nav.getByRole("link", { name: label })).toHaveAttribute(
      "href",
      `#${id}`
    )
    await expect(page.locator(`#${id}`)).toBeVisible()
  }
})

test("Ein Klick auf Meta scrollt zur Meta-Überschrift", async ({ page }) => {
  await submitMockedAudit(page, buildReport({ findings: [FINDING] }))
  const nav = page.getByRole("navigation", { name: "Abschnitte dieser Prüfung" })
  await nav.getByRole("link", { name: "Meta" }).click()
  await expect(page).toHaveURL(/#padnext-meta-heading$/)
  await expect(page.locator("#padnext-meta-heading")).toBeInViewport()
})
