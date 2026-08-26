import path from "node:path"

/**
 * Where the signed-in cookie is parked between the `setup` project and every test that follows.
 *
 * Its own module, one constant, because `playwright.config.ts` and `auth.setup.ts` both need it and
 * neither can import the other: the config importing the setup would execute a `test()` call while
 * Playwright is still loading the config, which it refuses; the setup importing the config would be
 * a cycle.
 *
 * Git-ignored. The file it names is a live session for a live application, not a fixture.
 */
export const STORAGE_STATE = path.join(import.meta.dirname, ".auth/state.json")
