import { expect, test } from "@playwright/test"

/**
 * The pilot's whole signup form: email, password, organisation — and nothing else.
 *
 * Runs signed out, like `auth-guard.spec.ts` — a fresh registration is exactly the state that spec
 * does not cover. A new email every run (`Date.now()`) rather than a fixed one: unlike
 * `auth.setup.ts`'s shared account, this spec's entire point is the *first* run, and reusing an
 * address would exercise `USER_ALREADY_EXISTS` on the second run instead of what this asserts.
 *
 * Three things are checked, in the order a reader would notice them going wrong: the three labels
 * on the form (no phone, no address, no personal name — see the signup brief this guards), that
 * submitting them succeeds at all, and that the account lands on an organisation already active
 * rather than "Keine Organisation" — the whole reason `signup-form.tsx` calls
 * `organization.create` and `.setActive` in the same submit instead of leaving that to the sidebar
 * prompt.
 *
 * `@e2e.azmoth.test` — the domain this repository documents as admitted for testing (see
 * `docs/api/E2E_GOLDEN.md` and `auth.setup.ts`, which signs in under the same domain): a spec that
 * must go through the sign-up gate itself needs an address the gate actually admits, and this is
 * the one every e2e fixture in this repository agrees on rather than each spec inventing its own.
 */
test.use({ storageState: { cookies: [], origins: [] } })

test("Registrierung verlangt nur E-Mail, Passwort und Organisation", async ({
  page,
}) => {
  const email = `signup-${Date.now()}@e2e.azmoth.test`
  const password = "pilot-durchlauf-passwort-2026"
  const organization = `E2E Testorganisation ${Date.now()}`

  await page.goto("/signup")

  // Exactly these four inputs — email, password, its confirmation, and the organisation's name.
  // No "Vorname"/"Nachname", no phone number, no address: the assertion that those are gone is
  // this locator finding nothing else to fill in before the submit below succeeds.
  await page.getByLabel("Organisation").fill(organization)
  await page.getByLabel("E-Mail").fill(email)
  await page.getByLabel("Passwort", { exact: true }).fill(password)
  await page.getByLabel("Passwort bestätigen").fill(password)

  await page
    .getByRole("button", { name: "Registrieren", exact: true })
    .click()

  // Straight to the dashboard — no `/onboarding` detour, and no allowlist refusal in a development
  // server, which is what `pnpm dev` runs as (see `lib/auth-allowlist.ts`).
  await expect(
    page.getByRole("heading", { name: "Übersicht", level: 1 })
  ).toBeVisible()

  // The organisation named on the form is the session's active one already — not "Keine
  // Organisation" waiting for a manual `window.prompt` in the rail.
  await expect(
    page.getByRole("button", { name: "Organisation wechseln" })
  ).toContainText(organization)
})

/**
 * The bug this guards: `signup-form.tsx` used to map every sign-up failure to the same generic
 * fallback sentence because its error map keyed on `USER_ALREADY_EXISTS`, a code the installed
 * `better-auth`'s `sign-up/email` route never actually throws — the real one is
 * `USER_ALREADY_EXISTS_USE_ANOTHER_EMAIL` (see `components/auth/auth-messages.ts`). Registering
 * twice with the same address is what exercises that exact code over the wire.
 */
test("eine zweite Registrierung mit derselben E-Mail zeigt die Dublettenmeldung mit Anmelde-Link", async ({
  page,
}) => {
  const email = `duplicate-${Date.now()}@e2e.azmoth.test`
  const password = "pilot-durchlauf-passwort-2026"

  await page.goto("/signup")
  await page.getByLabel("Organisation").fill("Erstregistrierung")
  await page.getByLabel("E-Mail").fill(email)
  await page.getByLabel("Passwort", { exact: true }).fill(password)
  await page.getByLabel("Passwort bestätigen").fill(password)
  await page
    .getByRole("button", { name: "Registrieren", exact: true })
    .click()

  await expect(
    page.getByRole("heading", { name: "Übersicht", level: 1 })
  ).toBeVisible()

  // The first attempt signed this browser in — cleared here so the second attempt reaches the
  // sign-up form at all rather than being redirected away by `middleware.ts`'s "already signed in
  // has no business on `/signup`" rule.
  await page.context().clearCookies()
  await page.goto("/signup")
  await page.getByLabel("Organisation").fill("Zweitregistrierung")
  await page.getByLabel("E-Mail").fill(email)
  await page.getByLabel("Passwort", { exact: true }).fill(password)
  await page.getByLabel("Passwort bestätigen").fill(password)
  await page
    .getByRole("button", { name: "Registrieren", exact: true })
    .click()

  // `[data-slot="alert"]`, not `getByRole("alert")`: the first sign-up above already caused one
  // client-side navigation, and Next's own route announcer (`#__next-route-announcer__`) also
  // carries `role="alert"` from that point on — the two coexist, and `getByRole("alert")` is then
  // ambiguous. The `data-slot` is shadcn's `Alert` marking its own root.
  const alertBox = page.locator('[data-slot="alert"]')
  await expect(alertBox).toContainText("bereits registriert")
  await expect(
    alertBox.getByRole("link", { name: "Stattdessen anmelden" })
  ).toBeVisible()
})

/**
 * The character-class half of the password policy — see `lib/password-policy.ts` — is enforced
 * only in the browser, so this is the one place it is covered at all. Thirteen lowercase letters
 * and digits clear the length floor but match only two of the four classes, which is what the
 * rejection message below names.
 */
test("ein Passwort mit zu wenig Zeichenarten wird abgelehnt, bevor irgendetwas abgeschickt wird", async ({
  page,
}) => {
  const email = `weak-password-${Date.now()}@e2e.azmoth.test`

  await page.goto("/signup")
  await page.getByLabel("Organisation").fill("Schwaches Passwort GmbH")
  await page.getByLabel("E-Mail").fill(email)
  await page.getByLabel("Passwort", { exact: true }).fill("nurklein12345")
  await page.getByLabel("Passwort bestätigen").fill("nurklein12345")
  await page
    .getByRole("button", { name: "Registrieren", exact: true })
    .click()

  // See the `data-slot="alert"` note in the duplicate-email test above.
  await expect(page.locator('[data-slot="alert"]')).toContainText(
    "weitere Zeichenart"
  )
  // Still on the form: the field the browser did not clear is the tell that this was rejected
  // before `signUp.email` was ever called.
  await expect(page.getByLabel("E-Mail")).toHaveValue(email)
})
