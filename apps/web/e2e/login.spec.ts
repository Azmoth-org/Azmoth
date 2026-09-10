import { expect, test } from "@playwright/test"

/**
 * The login form's error-code mapping, through the actual page rather than by calling
 * `authErrorMessage` in isolation — `apps/web` has no unit-test runner (see `package.json`;
 * `test:e2e` is the only test script), so this is the coverage that exists for it.
 *
 * Runs signed out, like `signup.spec.ts` — a login attempt is exactly the state
 * `auth.setup.ts`'s shared session skips past.
 */
test.use({ storageState: { cookies: [], origins: [] } })

test("eine falsche Anmeldung zeigt die deutsche Meldung statt Better Auths Fehlercode", async ({
  page,
}) => {
  await page.goto("/login")

  await page.getByLabel("E-Mail").fill("nobody@e2e.azmoth.test")
  await page.getByLabel("Passwort").fill("ganz-bestimmt-falsch")
  await page.getByRole("button", { name: "Anmelden", exact: true }).click()

  const alertBox = page.getByRole("alert")
  await expect(alertBox).toContainText(
    "E-Mail-Adresse oder Passwort ist falsch"
  )
  // The failure this guards: rendering Better Auth's own `code`/English `message` verbatim instead
  // of the German sentence above.
  await expect(alertBox).not.toContainText("INVALID_EMAIL_OR_PASSWORD")
  await expect(alertBox).not.toContainText("USER_NOT_FOUND")
})
