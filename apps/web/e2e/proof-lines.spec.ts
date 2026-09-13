import { expect, test } from "@playwright/test"

import { PROPOSAL_ID, buildProposal } from "./fixtures/proposal"

/**
 * Proof-line counters read as explicit German text, not a bare `(6)`, and are still clickable to
 * open the full proof tree. Mocking `GET /api/engine/proposals/{id}` drives `/review?id=...`
 * deterministically, the same way `positionen-table.spec.ts` mocks the PADnext audit endpoint.
 */

const PROOF_STEPS = [
  { rule: "eligible", rule_id: "r1", legal_basis: "§ 1 GOÄ", detail: "Grundvoraussetzung erfüllt.", ziffer: "1" },
  { rule: "factor_ok", rule_id: "r2", legal_basis: "§ 5 GOÄ", detail: "Faktor im zulässigen Bereich.", ziffer: "1" },
]

const LINE_WITH_PROOF = {
  ziffer: "1",
  official_text: "Beratung",
  amount_eur: "23.24",
  amount_eur_before_minderung: "23.24",
  factor: "2.3",
  factor_basis: "schwellenwert",
  punkte: 80,
  status: "billable",
  is_analog: false,
  justification_present: false,
  justification_required: false,
  minderung_applied: false,
  proof: PROOF_STEPS,
}

const LINE_WITHOUT_PROOF = {
  ziffer: "2",
  official_text: "Zuschlag ohne Beweiszeilen",
  amount_eur: "10.00",
  amount_eur_before_minderung: "10.00",
  factor: "1.0",
  factor_basis: "einfachsatz",
  punkte: 20,
  status: "billable",
  is_analog: false,
  justification_present: false,
  justification_required: false,
  minderung_applied: false,
  proof: [] as unknown[],
}

test.beforeEach(async ({ page }) => {
  await page.route(`**/api/engine/proposals/${PROPOSAL_ID}`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(
        buildProposal({ proposed_codes: [LINE_WITH_PROOF, LINE_WITHOUT_PROOF] })
      ),
    })
  )
  await page.goto(`/review?id=${PROPOSAL_ID}`)
  await expect(page.getByText("Akzeptierte Positionen")).toBeVisible()
})

test("zeigt die Beweiszeilen-Anzahl als Text statt kryptischem Zähler", async ({
  page,
}) => {
  await expect(page.getByText("(2)")).toHaveCount(0)
  const trigger = page.getByRole("button", { name: "2 Beweiszeilen" })
  await expect(trigger).toBeVisible()
})

test("Beweiszeilen-Zähler öffnet den Beweisbaum mit den einzelnen Schritten", async ({
  page,
}) => {
  await page.getByRole("button", { name: "2 Beweiszeilen" }).click()
  await expect(page.getByRole("dialog")).toBeVisible()
  await expect(page.getByText("eligible")).toBeVisible()
  await expect(page.getByText("factor_ok")).toBeVisible()
  await expect(page.getByText("Grundvoraussetzung erfüllt.")).toBeVisible()
})

test("keine Beweiszeilen: expliziter Leerzustand statt eines stummen Buttons", async ({
  page,
}) => {
  await expect(
    page.getByText("Keine Beweiszeilen für diesen Eintrag.")
  ).toBeVisible()
  await expect(
    page.getByRole("button", { name: /Beweiszeile/ })
  ).toHaveCount(1) // only the line that actually has proof steps gets a button
})
