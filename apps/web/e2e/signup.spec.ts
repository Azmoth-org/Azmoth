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
 * `@e2e.azmoth.test`, not `.invalid` — this repository's `SIGNUP_ALLOWLIST` (see `.env` /
 * `.env.example`) admits that domain for exactly this reason: `auth.setup.ts`'s shared account is
 * grandfathered in by already existing, but a spec that must go through the sign-up gate itself
 * needs an address the gate actually admits.
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
