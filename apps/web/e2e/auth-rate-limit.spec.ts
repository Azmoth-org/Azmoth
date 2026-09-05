import { expect, test } from "@playwright/test"

/**
 * The credential endpoints refuse a sixth attempt in a minute; the session endpoint never does.
 *
 * Here rather than in a unit test because the interesting part is not the counter — that is
 * arithmetic, and `lib/rate-limit.ts` is where it lives — but the *wiring*: that `middleware.ts`
 * runs the limiter before `PUBLIC_PREFIXES` returns early, that it counts the paths Better Auth
 * actually serves under, and above all that it does **not** count the one the client polls. Each of
 * those is a whole-request property, and each of them typechecks perfectly while being wrong.
 *
 * The second test is the one worth keeping. A limiter over `/api/auth/*` as a whole would pass every
 * assertion about refusing sign-ins and would present in production as users being signed out for
 * reading their own dashboard — an authentication bug wearing a security control's clothes.
 *
 * ## Why these requests are `request.post` and not a filled-in form
 *
 * The limiter reads the address and the path, not the body. Driving the login form six times would
 * assert the same thing far more slowly, and would additionally depend on the form's markup and on
 * a seeded account existing — neither of which this behaviour has anything to do with. The
 * credentials below are deliberately wrong: what is being counted is the *attempt*.
 */

test.use({ storageState: { cookies: [], origins: [] } })

/** Matches `LIMIT` in `lib/rate-limit.ts`. */
const LIMIT = 5

/**
 * A distinct source address per test.
 *
 * The counter is per IP and lives in the server process for a full minute, so two specs sharing an
 * address would make the second one's result depend on the first one's — and on whether Playwright
 * ran them in the same worker. Setting `X-Forwarded-For` gives each its own bucket.
 *
 * That this works at all is worth noting: `clientAddress` reads the **last** hop, so in a real
 * deployment Caddy's appended address wins and a client cannot choose its own bucket this way. Here
 * there is no proxy, so the header's only entry is also its last. If this spec ever starts running
 * against a deployment behind Caddy, these headers will stop having any effect — which is the
 * limiter working correctly, not the test breaking.
 */
function source(id: string): Record<string, string> {
  return { "x-forwarded-for": `203.0.113.${id}` }
}

test("der sechste Anmeldeversuch pro Minute wird mit 429 abgewiesen", async ({
  request,
}) => {
  const headers = source("10")
  const attempt = () =>
    request.post("/api/auth/sign-in/email", {
      headers,
      data: { email: "nobody@example.invalid", password: "wrong-password" },
      failOnStatusCode: false,
    })

  // The budget. Each of these is refused as a *credential* — 401/400 — and that is the point: a
  // failed sign-in still spends an attempt, or the limiter would defend nothing.
  for (let i = 0; i < LIMIT; i++) {
    const response = await attempt()
    expect(response.status(), `attempt ${i + 1} should not be rate limited`).not.toBe(429)
  }

  const refused = await attempt()
  expect(refused.status()).toBe(429)

  // A `429` without `Retry-After` tells a client to back off for an unknown period, which in
  // practice means it retries immediately.
  const retryAfter = Number(refused.headers()["retry-after"])
  expect(retryAfter).toBeGreaterThan(0)
  expect(retryAfter).toBeLessThanOrEqual(60)

  const body = await refused.json()
  expect(body.error).toBe("rate_limit_exceeded")
  // Both languages, like every other message a practice can see.
  expect(body.message).toContain("Anmeldeversuche")
  expect(body.message).toContain("Too many sign-in attempts")
})

test("die Sitzungsabfrage wird niemals begrenzt", async ({ request }) => {
  /**
   * `/api/auth/get-session` is called on mount, on window focus and on every session refresh. If it
   * were inside the budget, a signed-in user browsing normally would be signed out — so this asserts
   * well past the limit.
   */
  const headers = source("20")

  for (let i = 0; i < LIMIT * 4; i++) {
    const response = await request.get("/api/auth/get-session", {
      headers,
      failOnStatusCode: false,
    })
    expect(response.status(), `get-session call ${i + 1} must not be limited`).not.toBe(429)
  }
})

test("die Registrierung teilt sich nicht das Budget einer anderen IP", async ({
  request,
}) => {
  /** Per address, not global — otherwise one script locks out every practice at once. */
  const spender = source("30")
  for (let i = 0; i < LIMIT + 1; i++) {
    await request.post("/api/auth/sign-up/email", {
      headers: spender,
      data: { email: `a${i}@example.invalid`, password: "irrelevant", name: "x" },
      failOnStatusCode: false,
    })
  }

  const other = await request.post("/api/auth/sign-up/email", {
    headers: source("31"),
    data: { email: "fresh@example.invalid", password: "irrelevant", name: "x" },
    failOnStatusCode: false,
  })

  expect(other.status()).not.toBe(429)
})

test("ein GET auf die Anmeldeseite verbraucht kein Budget", async ({
  request,
}) => {
  /**
   * Only `POST` is counted. A reader who reloads `/login` six times — or a browser that prefetches
   * it — must still be able to sign in, and the OAuth callback arrives as a `GET` on a path under
   * `/api/auth/sign-in` too.
   */
  const headers = source("40")

  for (let i = 0; i < LIMIT * 2; i++) {
    const response = await request.get("/login", { headers, failOnStatusCode: false })
    expect(response.status()).not.toBe(429)
  }

  const signIn = await request.post("/api/auth/sign-in/email", {
    headers,
    data: { email: "nobody@example.invalid", password: "wrong-password" },
    failOnStatusCode: false,
  })
  expect(signIn.status()).not.toBe(429)
})
