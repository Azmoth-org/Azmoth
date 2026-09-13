import { expect, test } from "@playwright/test"

import { PROPOSAL_ID, buildProposal } from "./fixtures/proposal"

/**
 * Repeated engine hints fold into one summary row, and nothing is permanently hidden behind it.
 *
 * Mocking `GET /api/engine/proposals/{id}` and visiting `/review?id=...` drives the whole deep-link
 * path deterministically — the same approach `positionen-table.spec.ts` uses for `/padnext` — so
 * this is independent of a running engine.
 */

const REPEATED_TYPE_WARNINGS = [
  {
    type: "rule_coverage_incomplete",
    message: "Die Regelabdeckung ist unvollständig.",
    severity: "warning",
    ziffer: "1",
    rule_id: "r1",
    legal_basis: "",
  },
  {
    type: "rule_coverage_incomplete",
    message: "Die Regelabdeckung ist unvollständig.",
    severity: "warning",
    ziffer: "2",
    rule_id: "r2",
    legal_basis: "",
  },
  {
    type: "rule_coverage_incomplete",
    message: "Die Regelabdeckung ist unvollständig.",
    severity: "warning",
    ziffer: "3",
    rule_id: "r3",
    legal_basis: "",
  },
  {
    type: "rule_coverage_incomplete",
    message: "Die Regelabdeckung ist unvollständig.",
    severity: "warning",
    ziffer: "4",
    rule_id: "r4",
    legal_basis: "",
  },
  {
    type: "rule_coverage_incomplete",
    message: "Die Regelabdeckung ist unvollständig.",
    severity: "warning",
    ziffer: "5",
    rule_id: "r5",
    legal_basis: "",
  },
  {
    type: "rule_coverage_incomplete",
    message: "Die Regelabdeckung ist unvollständig.",
    severity: "warning",
    ziffer: "6",
    rule_id: "r6",
    legal_basis: "",
  },
  // A distinct type, once — must stay its own ungrouped row alongside the group of six.
  {
    type: "justification_missing",
    message: "Eine Begründung fehlt.",
    severity: "error",
    ziffer: "9",
    rule_id: "r9",
    legal_basis: "§ 12 Abs. 3 GOÄ",
  },
]

test.describe("Hinweise der Engine — Gruppierung", () => {
  test.beforeEach(async ({ page }) => {
    await page.route(`**/api/engine/proposals/${PROPOSAL_ID}`, (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(
          buildProposal({ warnings: REPEATED_TYPE_WARNINGS })
        ),
      })
    )
    await page.goto(`/review?id=${PROPOSAL_ID}`)
    await expect(page.getByText("Hinweise der Engine")).toBeVisible()
  })

  test("sechs gleichartige Hinweise werden zu einer Sammelzeile mit Live-Zähler", async ({
    page,
  }) => {
    await expect(
      page.getByText("Regelabdeckung unvollständig · 6 Hinweise")
    ).toBeVisible()

    // A distinct type does not get folded into the group — it stays its own row.
    await expect(page.getByText("Begründung fehlt")).toBeVisible()

    // Never hidden permanently: the six Ziffern are not on screen before the row is expanded.
    await expect(page.getByText("Betroffene Ziffern")).not.toBeVisible()
  })

  test("Hinweise anzeigen/ausblenden schaltet die Erweiterung um, ohne Details zu löschen", async ({
    page,
  }) => {
    const toggle = page.getByRole("button", { name: "Hinweise anzeigen" })
    await expect(toggle).toBeVisible()

    await toggle.click()
    await expect(
      page.getByRole("button", { name: "Hinweise ausblenden" })
    ).toBeVisible()
    await expect(page.getByText("Betroffene Ziffern")).toBeVisible()
    for (const ziffer of ["1", "2", "3", "4", "5", "6"]) {
      await expect(page.getByText(`GOÄ ${ziffer}`, { exact: true })).toBeVisible()
    }
    // Every underlying warning's identifier is still reachable, not just the chips.
    await expect(page.getByText("rule_coverage_incomplete")).toHaveCount(6)

    await page.getByRole("button", { name: "Hinweise ausblenden" }).click()
    await expect(
      page.getByRole("button", { name: "Hinweise anzeigen" })
    ).toBeVisible()
    await expect(page.getByText("Betroffene Ziffern")).not.toBeVisible()
  })
})
