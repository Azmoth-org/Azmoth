import { expect, test as setup, type APIRequestContext } from "@playwright/test"

import { STORAGE_STATE } from "./storage-state"

/**
 * Sign in once, and hand the session to every spec.
 *
 * Every screen is behind Better Auth now, so a spec that navigates to `/` without a session is
 * redirected to `/login` and asserts on a form. This runs first — Playwright's `dependencies` wire
 * it in front of the browser project — and writes the resulting cookie to `STORAGE_STATE`, which
 * each test then starts from. One sign-in for the whole run rather than one per test: the flow
 * being smoke-tested is the dashboard, and paying for a round-trip through the auth endpoints
 * before each spec would make the suite slower without testing anything new.
 *
 * ## The account
 *
 * Created if it is not there, reused if it is. `sign-up` answers `USER_ALREADY_EXISTS` on the second
 * run and that is not a failure — it is the normal case on any machine the suite has run on before.
 * The `.invalid` TLD is reserved by RFC 2606 and can never be a real address, which is the point:
 * this row will sit in a developer's database, and it must be impossible to mistake for a colleague
 * or to accidentally mail.
 *
 * It is a real account with real access, so this is also the reminder that the e2e suite writes to
 * whatever database the app under test is pointed at. That is already true of the proposals the
 * smoke test reads; it is now true of a user row as well.
 */
const EMAIL = "e2e@azmoth.invalid"
const PASSWORD = "e2e-durchlauf-passwort-2026"
const NAME = "E2E Durchlauf"

setup("angemeldet", async ({ page, request }) => {
  await signUpIfNeeded(request)

  // Through the form rather than the API, because this is also the only coverage the login screen
  // gets: if the inputs stop being labelled or the submit stops calling `signIn`, the whole suite
  // fails here with a screenshot of the reason instead of everywhere else with a redirect.
  await page.goto("/login")
  await page.getByLabel("E-Mail").fill(EMAIL)
  await page.getByLabel("Passwort").fill(PASSWORD)
  // `exact`, because Playwright matches an accessible name by substring by default and the Google
  // button next to this one is labelled "Mit Google anmelden". Without it the locator resolves to
  // two elements on any deployment that has GOOGLE_CLIENT_ID set, and the suite fails on strict
  // mode rather than on anything real.
  await page.getByRole("button", { name: "Anmelden", exact: true }).click()

  // The dashboard, not merely "not the login page": the redirect after sign-in is what makes the
  // session usable, and landing back on `/login` is exactly the failure this must not pass through.
  await expect(
    page.getByRole("heading", { name: "Übersicht", level: 1 })
  ).toBeVisible()

  await page.context().storageState({ path: STORAGE_STATE })
})

/** Create the account, treating "it already exists" as success. */
async function signUpIfNeeded(request: APIRequestContext): Promise<void> {
  const response = await request.post("/api/auth/sign-up/email", {
    data: { name: NAME, email: EMAIL, password: PASSWORD },
  })
  if (response.ok()) return

  const body = await response.text()
  expect(
    body.includes("USER_ALREADY_EXISTS"),
    `Das E2E-Konto konnte weder angelegt noch wiederverwendet werden (HTTP ${response.status()}): ${body}`
  ).toBe(true)
}
