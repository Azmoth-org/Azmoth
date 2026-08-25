import { defineConfig, devices } from "@playwright/test"

/**
 * Playwright, for the one thing this repository has no other way of catching: a frontend that
 * builds, typechecks and lints cleanly and still renders a broken screen.
 *
 * Deliberately small. There is exactly one spec — `e2e/dashboard-smoke.spec.ts` — and it walks the
 * core path a reader takes, dashboard to a stored proposal. It is a regression tripwire, not a test
 * suite, and it is configured like one: one browser, no retries, no fixtures of its own.
 *
 * ## What has to be running
 *
 * Two processes, because the dashboard is server-rendered and every figure on it comes from the
 * engine:
 *
 * * **the web app**, on `baseURL` below — started automatically by the `webServer` block if it is
 *   not already up;
 * * **the engine**, on whatever `ENGINE_BASE_URL` the web app was started with (default
 *   `http://localhost:8000`) — NOT started here. Playwright cannot bring up Soufflé, Clingo and a
 *   database, and a smoke test that silently passed against a dead engine would be worse than no
 *   smoke test: the dashboard renders "Engine nicht erreichbar" perfectly well.
 *
 * The spec fails with a sentence naming the missing engine rather than a locator timeout, so the
 * distinction between "the UI regressed" and "you forgot to start the backend" survives to the
 * terminal. See the header of the spec for the commands.
 */

/**
 * Where the app under test lives. Overridable so the suite can be pointed at a dev server on a
 * spare port, or at the container from `infra/docker/docker-compose.yml`, without editing this file.
 */
const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000"

/** The port `next dev` has to be told about, so `webServer` starts the app where the tests look. */
const port = new URL(baseURL).port || "3000"

export default defineConfig({
  testDir: "./e2e",

  /** Per test. The flow is three navigations; anything near this is a hang, not a slow machine. */
  timeout: 30_000,

  /**
   * Well under the per-test budget, and above a cold `next dev` compile of a route — the first
   * visit to `/` in a dev server pays for a compile that a production build does not.
   */
  expect: { timeout: 10_000 },

  fullyParallel: true,

  /** A committed `test.only` silently skips the rest of the suite. In CI that is a failure. */
  forbidOnly: Boolean(process.env.CI),

  /**
   * No retries, on purpose. One flaky-passing smoke test teaches people to re-run it; one that
   * fails outright gets looked at.
   */
  retries: 0,

  reporter: process.env.CI ? [["list"], ["github"]] : [["list"]],

  use: {
    baseURL,
    /** German UI, German assertions — the browser should agree about dates and number formatting. */
    locale: "de-DE",
    timezoneId: "Europe/Berlin",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },

  /** Chromium only. A second engine doubles the run for a test that asserts on text and links. */
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],

  /**
   * `reuseExistingServer` is unconditional, CI included. The app is also what the Docker stack
   * serves, and a run pointed at a container must not try to start a second Next.js over it.
   */
  webServer: {
    command: `pnpm dev --port ${port}`,
    url: baseURL,
    reuseExistingServer: true,
    timeout: 120_000,
    stdout: "ignore",
    stderr: "pipe",
  },
})
