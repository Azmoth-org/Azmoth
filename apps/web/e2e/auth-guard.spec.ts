import { expect, test } from "@playwright/test"

/**
 * The gate: without a session, every screen is `/login` and nothing else.
 *
 * This is the one spec that runs *signed out* — `storageState: undefined` overrides the project's
 * saved session — because the property it asserts only exists in that state. It is here for the
 * same reason the dashboard smoke test is: `middleware.ts` and `app/(app)/layout.tsx` both
 * typecheck perfectly while protecting nothing, and the failure is silent in exactly the way that
 * matters most.
 *
 * The list is the protected routes named in the brief. Kept explicit rather than derived from
 * `NAV_ITEMS`, because a test that generated its expectations from the same list the application
 * navigates by would pass if an entry were removed from both.
 */
const PROTECTED = [
  "/",
  "/review",
  "/proposals",
  "/padnext",
  "/padnext/batch",
  "/padnext/batch/history",
  "/rules",
] as const

test.use({ storageState: { cookies: [], origins: [] } })

for (const route of PROTECTED) {
  test(`${route} verlangt eine Anmeldung`, async ({ page }) => {
    await page.goto(route)

    await expect(page).toHaveURL(/\/login/)
    await expect(page.getByRole("heading", { name: "Anmelden" })).toBeVisible()
  })
}

test("die Anmeldeseite selbst ist öffentlich", async ({ page }) => {
  await page.goto("/login")

  await expect(page.getByLabel("E-Mail")).toBeVisible()
  await expect(page.getByRole("link", { name: "Registrieren" })).toBeVisible()
})

/**
 * A failed Google sign-in comes back as a redirect carrying `?error=<code>`, which is the only way
 * that failure can be reported — there is no response for a component to catch. Two properties are
 * worth holding: the code becomes a German sentence, and the code itself never reaches the page.
 *
 * The second one is the reason this test exists at all. That parameter is in a URL anyone can send,
 * and part of its vocabulary comes from Google rather than from us; a login screen that rendered it
 * verbatim would display whatever a phishing link put there. Both cases run without any Google
 * configuration, because the page reads the parameter regardless of whether the button is shown.
 */
test("eine fehlgeschlagene Google-Anmeldung wird auf Deutsch erklärt", async ({ page }) => {
  await page.goto("/login?error=account_not_linked")

  await expect(page.getByRole("alert")).toContainText("Passwort")
})

test("ein unbekannter Fehlercode wird nicht in die Seite geschrieben", async ({ page }) => {
  await page.goto(`/login?error=${encodeURIComponent("<b>nicht-echt</b>")}`)

  await expect(page.getByRole("alert")).toContainText("Anmeldung mit Google ist fehlgeschlagen")
  await expect(page.getByText("nicht-echt")).toHaveCount(0)
})

test("ein API-Aufruf ohne Sitzung wird abgelehnt, nicht umgeleitet", async ({ request }) => {
  // A redirect here would be worse than a refusal: `fetch` follows it, receives the login page's
  // HTML with status 200, and the caller reports "invalid JSON from the engine" — a wrong answer to
  // a question that has a right one.
  const response = await request.get("/api/engine/rules/coverage", { maxRedirects: 0 })

  expect(response.status()).toBe(401)
  expect(await response.json()).toMatchObject({ error: "unauthenticated" })
})
